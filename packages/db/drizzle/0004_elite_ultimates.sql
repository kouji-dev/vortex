CREATE TABLE "failed_billing_events" (
	"id" text PRIMARY KEY NOT NULL,
	"kind" text NOT NULL,
	"payload" jsonb,
	"error" text,
	"retry_count" integer DEFAULT 0 NOT NULL,
	"next_retry_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "stripe_events" (
	"id" text PRIMARY KEY NOT NULL,
	"type" text,
	"created" timestamp with time zone,
	"processed_at" timestamp with time zone
);
--> statement-breakpoint
ALTER TABLE "plan_entitlements" ADD COLUMN "org_budget_micro" bigint;--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN "last_event_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "usage_records" ADD COLUMN "usage_estimated" boolean DEFAULT false NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX "credit_ledger_request_id_uq" ON "credit_ledger" USING btree ("request_id") WHERE "credit_ledger"."request_id" is not null;--> statement-breakpoint
-- dedupe platform_admins per user (keep the oldest row) before enforcing uniqueness
DELETE FROM "platform_admins" WHERE "id" IN (
	SELECT "id" FROM (
		SELECT "id", row_number() OVER (
			PARTITION BY "user_id"
			ORDER BY "created_at" ASC, "id" ASC
		) AS rn
		FROM "platform_admins"
	) ranked WHERE ranked.rn > 1
);--> statement-breakpoint
CREATE UNIQUE INDEX "platform_admins_user_uq" ON "platform_admins" USING btree ("user_id");--> statement-breakpoint
-- dedupe subscriptions per org before enforcing uniqueness:
-- keep the row with a stripe_subscription_id, else the newest
DELETE FROM "subscriptions" WHERE "id" IN (
	SELECT "id" FROM (
		SELECT "id", row_number() OVER (
			PARTITION BY "org_id"
			ORDER BY ("stripe_subscription_id" IS NOT NULL) DESC, "created_at" DESC, "id" ASC
		) AS rn
		FROM "subscriptions"
	) ranked WHERE ranked.rn > 1
);--> statement-breakpoint
CREATE UNIQUE INDEX "subscriptions_org_uq" ON "subscriptions" USING btree ("org_id");