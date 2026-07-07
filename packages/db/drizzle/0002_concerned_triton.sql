CREATE TYPE "public"."contract_status" AS ENUM('draft', 'active', 'expired', 'canceled');--> statement-breakpoint
CREATE TYPE "public"."key_mode" AS ENUM('byok', 'managed', 'hybrid');--> statement-breakpoint
CREATE TYPE "public"."meter_type" AS ENUM('requests', 'input_tokens', 'output_tokens', 'cost_micro', 'seats', 'service_accounts');--> statement-breakpoint
CREATE TYPE "public"."pricing_scope" AS ENUM('plan', 'contract');--> statement-breakpoint
CREATE TABLE "contracts" (
	"id" text PRIMARY KEY NOT NULL,
	"org_id" text NOT NULL,
	"base_micro" bigint,
	"seat_commit" integer,
	"status" "contract_status" DEFAULT 'active' NOT NULL,
	"term_start" timestamp with time zone,
	"term_end" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "credit_ledger" (
	"id" text PRIMARY KEY NOT NULL,
	"org_id" text NOT NULL,
	"delta_micro" bigint NOT NULL,
	"reason" text NOT NULL,
	"request_id" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "credit_wallets" (
	"id" text PRIMARY KEY NOT NULL,
	"org_id" text NOT NULL,
	"balance_micro" bigint DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "credit_wallets_org_id_unique" UNIQUE("org_id")
);
--> statement-breakpoint
CREATE TABLE "managed_provider_keys" (
	"id" text PRIMARY KEY NOT NULL,
	"provider" text NOT NULL,
	"label" text,
	"region" text,
	"options" jsonb,
	"encrypted_key" text NOT NULL,
	"price_override" jsonb,
	"health_status" "cred_health" DEFAULT 'valid' NOT NULL,
	"enabled" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "plan_entitlements" (
	"id" text PRIMARY KEY NOT NULL,
	"plan_id" text NOT NULL,
	"seats_per_org" integer,
	"service_per_member" integer,
	"team_budget_micro" bigint,
	"rpm" integer,
	"tpm" integer,
	"concurrency" integer,
	"flags" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "plan_entitlements_plan_id_unique" UNIQUE("plan_id")
);
--> statement-breakpoint
CREATE TABLE "pricing_tiers" (
	"id" text PRIMARY KEY NOT NULL,
	"scope_type" "pricing_scope" NOT NULL,
	"scope_id" text NOT NULL,
	"meter" "meter_type" NOT NULL,
	"up_to_qty" bigint,
	"unit_price_micro" bigint NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "usage_rollups" (
	"id" text PRIMARY KEY NOT NULL,
	"org_id" text NOT NULL,
	"period" text NOT NULL,
	"meter" "meter_type" NOT NULL,
	"value" bigint DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "organizations" ADD COLUMN "key_mode" "key_mode" DEFAULT 'byok' NOT NULL;--> statement-breakpoint
ALTER TABLE "organizations" ADD COLUMN "markup_bps" integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE "contracts" ADD CONSTRAINT "contracts_org_id_organizations_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "credit_ledger" ADD CONSTRAINT "credit_ledger_org_id_organizations_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "credit_wallets" ADD CONSTRAINT "credit_wallets_org_id_organizations_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "plan_entitlements" ADD CONSTRAINT "plan_entitlements_plan_id_plans_id_fk" FOREIGN KEY ("plan_id") REFERENCES "public"."plans"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "usage_rollups" ADD CONSTRAINT "usage_rollups_org_id_organizations_id_fk" FOREIGN KEY ("org_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "credit_ledger_org_idx" ON "credit_ledger" USING btree ("org_id","created_at");--> statement-breakpoint
CREATE INDEX "pricing_tiers_scope_idx" ON "pricing_tiers" USING btree ("scope_type","scope_id","meter");--> statement-breakpoint
CREATE UNIQUE INDEX "usage_rollups_uq" ON "usage_rollups" USING btree ("org_id","period","meter");