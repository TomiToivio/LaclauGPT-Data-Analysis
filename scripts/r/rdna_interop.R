args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: rdna_interop.R statements.csv output.csv")
suppressPackageStartupMessages({library(data.table)})
dt <- fread(args[1], encoding = "UTF-8")
required <- c("statement_id", "actor_id", "concept_id", "source_url")
missing <- setdiff(required, names(dt))
if (length(missing) > 0) stop(paste("missing columns:", paste(missing, collapse = ", ")))
# This bridge intentionally preserves the DNA statement table as the stable handoff.
# Researchers may insert rDNA analysis calls here for their installed rDNA version,
# then export results with the same IDs plus method parameters and package version.
dt[, producer := "rDNA-compatible"]
dt[, interpretation_status := "DESCRIPTIVE_ONLY"]
fwrite(dt, args[2])
