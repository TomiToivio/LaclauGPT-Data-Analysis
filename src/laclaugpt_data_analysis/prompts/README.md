# Prompts
Prompts should be organized into directories as follows:
1) System Prompts in subdirectory system/
2) User Prompts in subdirectory user/

## System Prompts
System Prompt templates should be split into several major parts:
1) LaclauGPT description: description and role of LaclauGPT: AC/DT methodology, theory, writing conventions etc. Same for all projects.
2) Project description (AI26, EP24): detailed static description of current research project, research topic, theory and methodology. Different for each project.
3) Task description (Multimodal, Laclau): detailed description of each task in the pipeline. Has to contain detailed step by step description and output format (human-readable markdown and/or Pydantic JSON).

## User Prompts
User Prompt templates should be split into two major parts: 
1) Context/Memory: Current date, RAG results, other content/memory content. Previous analysis results. 
2) Content and Data: The content to be analyzed, including full metadata, text and multimodal data.
