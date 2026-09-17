args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: stm_interop.R input.parquet output.parquet")
suppressPackageStartupMessages({library(arrow); library(stm)})
df <- read_parquet(args[1])
if (!("text" %in% names(df))) stop("input requires text column")
processed <- textProcessor(df$text, metadata = df)
prep <- prepDocuments(processed$documents, processed$vocab, processed$meta)
set.seed(42)
fit <- stm(prep$documents, prep$vocab, K = 0, data = prep$meta, init.type = "Spectral")
theta <- as.data.frame(fit$theta)
theta$producer <- paste0("stm-", as.character(packageVersion("stm")))
theta$seed <- 42
theta$interpretation_status <- "DESCRIPTIVE_ONLY"
write_parquet(theta, args[2])
