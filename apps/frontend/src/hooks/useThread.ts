/**
 * useThread — manages a conversation thread end-to-end.
 *
 * Internally uses useStream for SSE; exposes a clean API to the page component.
 *
 * @param conversationId  null = "new conversation" composer mode (no thread yet).
 * @param opts.onStreamSuccess  Called after a stream completes without error.
 *                               Use to clear the compose draft.
 * @param opts.onConversationCreated  Called after a new conversation is created in
 *                                    composer mode. Use to navigate to the new thread.
 */
import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { CapabilityKey } from "~/components/chat/ChatComposerDock";
import { useConversationQuery } from "~/hooks/useConversationQuery";
import { useConversationMessagesTailQuery } from "~/hooks/useConversationMessagesTailQuery";
import { useStream } from "~/hooks/useStream";
import { getApiBase } from "~/lib/api-base";
import { getAuthHeaders } from "~/lib/authorizedFetch";
import { queryKeys } from "~/lib/queryKeys";
import {
  DEFAULT_CAPABILITIES,
  type CapabilityToggles,
  type ChatMessage,
  type Conversation,
  type ConversationSettings,
} from "~/lib/chat-types";

const MESSAGES_LIMIT = 100;
const MAX_ATTACHMENTS = 5;

export type UseThreadReturn = {
  // ── Conversation meta ─────────────────────────────────────────────────────
  conversation: Conversation | undefined;
  conversationPending: boolean;
  conversationError: Error | null;
  patchPending: boolean;
  deleteConversation: () => void;
  deletePending: boolean;
  deleteError: Error | null;

  // ── Messages ──────────────────────────────────────────────────────────────
  thread: ChatMessage[];
  /** True while the tail messages query is loading (useful for skeleton states). */
  threadPending: boolean;
  canLoadOlder: boolean;
  loadingOlder: boolean;
  loadOlder: () => Promise<void>;

  // ── Stream state ──────────────────────────────────────────────────────────
  streaming: boolean;
  streamingText: string;
  streamThreadItems: ReturnType<typeof useStream>["streamThreadItems"];
  sendError: string | null;
  setSendError: React.Dispatch<React.SetStateAction<string | null>>;
  retryStream: () => Promise<void>;
  stopStream: () => void;
  /** Ref to last request body, used to render a retry button when sendError is set. */
  lastStreamBodyRef: ReturnType<typeof useStream>["lastStreamBodyRef"];

  // ── Actions ───────────────────────────────────────────────────────────────
  /**
   * Send a message.
   * - In composer mode (conversationId == null): creates the conversation and
   *   calls onConversationCreated with the new id + bootstrap data.
   * - In thread mode: streams against the existing conversation.
   *   opts can override model/attachments/use_rag for the bootstrap replay case.
   */
  submitMessage: (text: string, opts?: SubmitOpts) => Promise<void>;
  regenerate: (assistantMessageId: number) => Promise<void>;

  // ── Model ─────────────────────────────────────────────────────────────────
  /** Current model slug stored for this conversation (or draft in composer mode). */
  chatModel: string;
  setChatModel: (m: string) => void;
  /** Patch the conversation with the new model (no-op in composer mode). */
  commitChatModel: (m: string) => void;

  // ── Capabilities ──────────────────────────────────────────────────────────
  capabilities: CapabilityToggles;
  setCapabilities: (next: CapabilityToggles) => void;
  toggleCapability: (key: CapabilityKey) => void;

  // ── KB ids (composer mode only) ───────────────────────────────────────────
  draftKbIds: number[];
  setDraftKbIds: React.Dispatch<React.SetStateAction<number[]>>;

  // ── Attachments ───────────────────────────────────────────────────────────
  /** Server-uploaded attachments for the next message (thread mode only). */
  pendingAttachments: { id: number; name: string }[];
  setPendingAttachments: React.Dispatch<
    React.SetStateAction<{ id: number; name: string }[]>
  >;
  /** Local File objects staged before conversation exists (composer mode only). */
  pendingComposerFiles: File[];
  setPendingComposerFiles: React.Dispatch<React.SetStateAction<File[]>>;
  /** Upload a file to the server and stage it for the next message. */
  uploadFile: (file: File) => Promise<void>;
};

export type ConversationBootstrap = {
  content: string;
  model?: string;
  use_rag: boolean;
  attachment_ids?: number[];
};

export type SubmitOpts = {
  /** Override the model for this message (used by bootstrap after navigation). */
  model?: string;
  /** Pre-uploaded attachment ids (used by bootstrap). */
  attachmentIds?: number[];
  /** Override use_rag (default true in thread mode). */
  use_rag?: boolean;
};

type UseThreadOptions = {
  onStreamSuccess?: () => void;
  onConversationCreated?: (
    conversationId: number,
    bootstrap: ConversationBootstrap,
  ) => void;
  onDeleteSuccess?: () => void;
};

export function useThread(
  conversationId: number | null,
  opts: UseThreadOptions = {},
): UseThreadReturn {
  const apiBase = getApiBase();
  const qc = useQueryClient();
  const { onStreamSuccess, onConversationCreated, onDeleteSuccess } = opts;

  // ── Stream (must come before tailQ so we can gate the query on !streaming) ──
  const {
    streaming,
    streamingText,
    streamThreadItems,
    sendError,
    setSendError,
    runStream,
    stopStream,
    retryStream: retryRaw,
    lastStreamBodyRef,
  } = useStream({ conversationId, apiBase, queryClient: qc });

  // ── Queries ───────────────────────────────────────────────────────────────
  const convQ = useConversationQuery(conversationId);
  // Disable the tail fetch while streaming: the SSE stream writes authoritative
  // data via setQueryData, and a concurrent fetch returning [] would overwrite
  // the optimistic user message (especially visible for brand-new conversations).
  const tailQ = useConversationMessagesTailQuery(
    conversationId,
    MESSAGES_LIMIT,
    { enabled: !streaming },
  );

  // ── Local state ───────────────────────────────────────────────────────────
  const [olderMessages, setOlderMessages] = React.useState<ChatMessage[]>([]);
  const [canLoadOlder, setCanLoadOlder] = React.useState(false);
  const [loadingOlder, setLoadingOlder] = React.useState(false);

  // In thread mode, modelDraft is kept in sync with the server value via the effect below.
  // In composer mode, it is purely local.
  const [chatModel, setChatModel] = React.useState("");

  // Capabilities: read from server in thread mode, local draft in composer mode.
  const [draftCaps, setDraftCaps] = React.useState<CapabilityToggles>({
    ...DEFAULT_CAPABILITIES,
  });

  const [draftKbIds, setDraftKbIds] = React.useState<number[]>([]);
  const [pendingAttachments, setPendingAttachments] = React.useState<
    { id: number; name: string }[]
  >([]);
  const [pendingComposerFiles, setPendingComposerFiles] = React.useState<
    File[]
  >([]);

  // ── Sync conversation state from server ───────────────────────────────────
  React.useEffect(() => {
    if (convQ.data) setChatModel(convQ.data.model ?? "");
  }, [convQ.data?.id, convQ.data?.model]);

  // Reset pagination + attachments when navigating between conversations.
  React.useEffect(() => {
    setOlderMessages([]);
    setCanLoadOlder(false);
    setPendingAttachments([]);
    setPendingComposerFiles([]);
    setDraftKbIds([]);
  }, [conversationId]);

  // Update canLoadOlder when fresh tail data arrives.
  React.useEffect(() => {
    if (tailQ.data == null) return;
    if (olderMessages.length === 0)
      setCanLoadOlder(tailQ.data.length >= MESSAGES_LIMIT);
  }, [tailQ.data, conversationId, olderMessages.length]);

  // ── Mutations ─────────────────────────────────────────────────────────────
  const patchConv = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      if (conversationId == null) throw new Error("No conversation");
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...(await getAuthHeaders()),
          },
          body: JSON.stringify(body),
        },
      );
      if (!res.ok) throw new Error(await res.text());
      return res.json() as Promise<Conversation>;
    },
    onSuccess: (data) => {
      if (conversationId == null) return;
      void qc.setQueryData(queryKeys.conversation(conversationId), data);
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() });
    },
  });

  const deleteConv = useMutation({
    mutationFn: async () => {
      if (conversationId == null) throw new Error("No conversation");
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}`,
        {
          method: "DELETE",
          headers: await getAuthHeaders(),
        },
      );
      if (!res.ok) throw new Error(await res.text());
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.conversations() });
      onDeleteSuccess?.();
    },
  });

  // ── Derived ───────────────────────────────────────────────────────────────
  const isComposerMode = conversationId == null;

  const capabilities: CapabilityToggles = isComposerMode
    ? draftCaps
    : (convQ.data?.settings?.capabilities ?? DEFAULT_CAPABILITIES);

  const thread = React.useMemo(
    () => [...olderMessages, ...(tailQ.data ?? [])],
    [olderMessages, tailQ.data],
  );

  // ── Capability management ─────────────────────────────────────────────────
  const setCapabilities = React.useCallback(
    (next: CapabilityToggles) => {
      if (isComposerMode) {
        setDraftCaps(next);
        return;
      }
      const prevSettings: ConversationSettings = convQ.data?.settings ?? {};
      patchConv.mutate({ settings: { ...prevSettings, capabilities: next } });
    },
    [isComposerMode, convQ.data?.settings, patchConv],
  );

  const toggleCapability = React.useCallback(
    (key: CapabilityKey) => {
      setCapabilities({ ...capabilities, [key]: !capabilities[key] });
    },
    [capabilities, setCapabilities],
  );

  // ── Model management ──────────────────────────────────────────────────────
  const commitChatModel = React.useCallback(
    (m: string) => {
      if (isComposerMode) return;
      const trimmed = m.trim();
      const current = convQ.data?.model ?? "";
      if (trimmed === current) return;
      patchConv.mutate({ model: trimmed || null });
    },
    [isComposerMode, convQ.data?.model, patchConv],
  );

  // ── Load older messages ───────────────────────────────────────────────────
  const loadOlder = React.useCallback(async () => {
    if (conversationId == null) return;
    const first = thread[0];
    if (!first || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const res = await fetch(
        `${apiBase}/api/chat/conversations/${conversationId}/messages?limit=${MESSAGES_LIMIT}&recent=true&before_id=${first.id}`,
        { headers: await getAuthHeaders() },
      );
      if (!res.ok) return;
      const chunk = (await res.json()) as ChatMessage[];
      if (chunk.length === 0) {
        setCanLoadOlder(false);
        return;
      }
      if (chunk.length < MESSAGES_LIMIT) setCanLoadOlder(false);
      setOlderMessages((prev) => [...chunk, ...prev]);
    } finally {
      setLoadingOlder(false);
    }
  }, [conversationId, thread, loadingOlder, apiBase]);

  // ── Upload helper ─────────────────────────────────────────────────────────
  const uploadFile = React.useCallback(
    async (file: File) => {
      if (isComposerMode) {
        setPendingComposerFiles((p) => [...p, file].slice(0, MAX_ATTACHMENTS));
        return;
      }
      if (conversationId == null) return;
      if (pendingAttachments.length >= MAX_ATTACHMENTS) return;
      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch(
          `${apiBase}/api/chat/conversations/${conversationId}/uploads`,
          { method: "POST", headers: await getAuthHeaders(), body: fd },
        );
        if (!res.ok) {
          setSendError(await res.text());
          return;
        }
        const j = (await res.json()) as {
          id: number;
          original_filename: string;
        };
        setPendingAttachments((p) =>
          [...p, { id: j.id, name: j.original_filename }].slice(
            0,
            MAX_ATTACHMENTS,
          ),
        );
      } catch (e) {
        setSendError(e instanceof Error ? e.message : "Upload failed");
      }
    },
    [
      isComposerMode,
      conversationId,
      pendingAttachments.length,
      apiBase,
      setSendError,
    ],
  );

  // ── Submit message ────────────────────────────────────────────────────────
  const submitMessage = React.useCallback(
    async (text: string, opts?: SubmitOpts) => {
      const trimmed = text.trim();
      const canSend =
        Boolean(trimmed) ||
        (!isComposerMode &&
          (opts?.attachmentIds?.length || pendingAttachments.length) > 0) ||
        (isComposerMode && pendingComposerFiles.length > 0);
      if (!canSend) return;

      if (isComposerMode) {
        // Create the conversation then hand off to the page for navigation.
        const settings: ConversationSettings = { capabilities: draftCaps };
        try {
          const res = await fetch(`${apiBase}/api/chat/conversations`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(await getAuthHeaders()),
            },
            body: JSON.stringify({
              title: null,
              assistant_id: null,
              model: chatModel.trim() || null,
              settings,
              knowledge_base_ids: draftKbIds,
            }),
          });
          if (!res.ok) {
            setSendError(await res.text());
            return;
          }
          const created = (await res.json()) as { id: number };

          // Upload any staged files.
          const attachment_ids: number[] = [];
          for (const f of pendingComposerFiles.slice(0, MAX_ATTACHMENTS)) {
            const fd = new FormData();
            fd.append("file", f);
            const up = await fetch(
              `${apiBase}/api/chat/conversations/${created.id}/uploads`,
              { method: "POST", headers: await getAuthHeaders(), body: fd },
            );
            if (!up.ok) {
              setSendError(await up.text());
              return;
            }
            attachment_ids.push(((await up.json()) as { id: number }).id);
          }
          setPendingComposerFiles([]);
          void qc.invalidateQueries({ queryKey: queryKeys.conversations() });

          // Pre-seed the messages cache before navigating so the new conversation
          // page mounts with fresh data (age ~0ms). staleTime: 30_000 then prevents
          // the tailQuery from firing a fetch on mount, which would return [] and
          // wipe the optimistic user message written by runStream.
          const optimisticContent =
            trimmed || (attachment_ids.length > 0 ? "(Attached files)" : "");
          qc.setQueryData(queryKeys.conversationMessagesTail(created.id), [
            {
              id: -1,
              conversation_id: created.id,
              role: "user" as const,
              content: optimisticContent,
              created_at: new Date().toISOString(),
              extra: null,
            },
          ]);

          onConversationCreated?.(created.id, {
            content:
              trimmed || (attachment_ids.length > 0 ? "(Attached files)" : ""),
            model: chatModel.trim() || undefined,
            use_rag: draftKbIds.length > 0,
            ...(attachment_ids.length > 0 ? { attachment_ids } : {}),
          });
        } catch (e) {
          setSendError(
            e instanceof Error ? e.message : "Could not start conversation",
          );
        }
        return;
      }

      // Thread mode: stream directly.
      const attachIds =
        opts?.attachmentIds ?? pendingAttachments.map((a) => a.id);
      const body: Record<string, unknown> = {
        content: trimmed || (attachIds.length > 0 ? "(Attached files)" : ""),
        use_rag: opts?.use_rag ?? true,
      };
      const modelToUse = opts?.model ?? chatModel.trim();
      if (modelToUse) body.model = modelToUse;
      if (attachIds.length > 0) body.attachment_ids = attachIds;

      await runStream(body, {
        onFinally: () => {
          setOlderMessages([]);
        },
        onSuccess: () => {
          setPendingAttachments([]);
          setSendError(null);
          onStreamSuccess?.();
        },
      });
    },
    [
      isComposerMode,
      pendingAttachments,
      pendingComposerFiles,
      draftCaps,
      chatModel,
      draftKbIds,
      apiBase,
      qc,
      runStream,
      setSendError,
      onStreamSuccess,
      onConversationCreated,
    ],
  );

  // ── Regenerate ────────────────────────────────────────────────────────────
  const regenerate = React.useCallback(
    async (assistantMessageId: number) => {
      const body: Record<string, unknown> = {
        content: "",
        regenerate_after_message_id: assistantMessageId,
        use_rag: true,
      };
      if (chatModel.trim()) body.model = chatModel.trim();
      await runStream(body, {
        onFinally: () => {
          setOlderMessages([]);
        },
      });
    },
    [chatModel, runStream],
  );

  // ── Retry wrapper (adds the same cleanup callbacks) ───────────────────────
  const retryStream = React.useCallback(
    () =>
      retryRaw({
        onFinally: () => {
          setOlderMessages([]);
        },
        onSuccess: () => {
          setPendingAttachments([]);
          onStreamSuccess?.();
        },
      }),
    [retryRaw, onStreamSuccess],
  );

  return {
    conversation: convQ.data,
    conversationPending: convQ.isPending,
    conversationError: convQ.error as Error | null,
    threadPending: tailQ.isPending,
    patchPending: patchConv.isPending,
    deleteConversation: () => deleteConv.mutate(),
    deletePending: deleteConv.isPending,
    deleteError: deleteConv.error as Error | null,

    thread,
    canLoadOlder,
    loadingOlder,
    loadOlder,

    streaming,
    streamingText,
    streamThreadItems,
    sendError,
    setSendError,
    retryStream,
    stopStream,
    lastStreamBodyRef,

    submitMessage,
    regenerate,

    chatModel,
    setChatModel,
    commitChatModel,

    capabilities,
    setCapabilities,
    toggleCapability,

    draftKbIds,
    setDraftKbIds,

    pendingAttachments,
    setPendingAttachments,
    pendingComposerFiles,
    setPendingComposerFiles,
    uploadFile,
  };
}
