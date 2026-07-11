CREATE TYPE "public"."model_family" AS ENUM('openai', 'anthropic', 'google');--> statement-breakpoint
DROP INDEX "models_provider_name_idx";--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "family" "model_family" DEFAULT 'openai' NOT NULL;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "upstream_model_id" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "max_output" integer;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "regions" jsonb;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "supported_features" jsonb;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "config" jsonb;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "custom_pricing" jsonb;--> statement-breakpoint
CREATE UNIQUE INDEX "models_provider_name_idx" ON "models" USING btree ("provider","model_name");