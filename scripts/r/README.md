# R interoperability

These scripts are optional, reproducible bridges between LaclauGPT open interchange files and mature R packages. They are intentionally standalone: core Python execution never requires R.

Preferred inputs/outputs are Parquet/Arrow, CSV, GraphML and JSON manifests. Every workflow should preserve source IDs, producer/package versions, parameters, random seed where applicable, and uncertainty/diagnostics.

Examples:

```bash
Rscript scripts/r/quanteda_interop.R input.parquet output_features.parquet
Rscript scripts/r/stm_interop.R input.parquet output_dir
Rscript scripts/r/rdna_interop.R statements.csv output_dir
Rscript scripts/r/igraph_interop.R graph.graphml output_metrics.csv
```

Install only the packages needed for the chosen workflow, for example `arrow`, `quanteda`, `stm`, `igraph`, `jsonlite`, `data.table`, `ggplot2`, and rDNA where available in the research environment.
