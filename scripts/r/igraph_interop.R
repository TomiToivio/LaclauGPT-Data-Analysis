args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: igraph_interop.R graph.graphml output.csv")
suppressPackageStartupMessages({library(igraph); library(data.table)})
g <- read_graph(args[1], format = "graphml")
out <- data.table(
  id = V(g)$name,
  degree = degree(g),
  betweenness = betweenness(g, normalized = TRUE),
  producer = paste0("igraph-", as.character(packageVersion("igraph"))),
  interpretation_status = "DESCRIPTIVE_ONLY"
)
fwrite(out, args[2])
