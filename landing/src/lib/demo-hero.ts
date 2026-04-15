export interface HeroDemoRefs {
  thread:    HTMLElement
  composer:  HTMLTextAreaElement
  charCount: HTMLElement
  sendBtn:   HTMLElement
}

export function startHeroDemo(_refs: HeroDemoRefs): () => void { return () => {} }
