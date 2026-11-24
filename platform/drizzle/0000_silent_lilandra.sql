CREATE TABLE `submissions` (
	`id` text PRIMARY KEY NOT NULL,
	`title` text NOT NULL,
	`source` text NOT NULL,
	`source_key` text NOT NULL,
	`demo` text,
	`repo` text,
	`theme` text NOT NULL,
	`notes` text,
	`status` text DEFAULT 'pending' NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `submissions_source_key_unique` ON `submissions` (`source_key`);