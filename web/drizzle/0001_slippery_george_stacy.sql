ALTER TABLE `atlas_entries` ADD `blocks` text DEFAULT '[]' NOT NULL;--> statement-breakpoint
ALTER TABLE `atlas_entries` ADD `revision` integer DEFAULT 0 NOT NULL;