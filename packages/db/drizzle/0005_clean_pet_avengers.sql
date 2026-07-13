ALTER TABLE "models" ADD COLUMN "cached_input_per_1k_micro" bigint;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "cache_write_per_1k_micro" bigint;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "modalities" jsonb;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "release_date" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "knowledge" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "last_updated" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "open_weights" boolean;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "description" text;