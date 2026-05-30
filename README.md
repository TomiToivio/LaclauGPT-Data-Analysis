# LaclauGPT: Data Analysis
LaclauGPT is a social science research framework. It is called LaclauGPT as a tribute to [Ernesto Laclau](https://en.wikipedia.org/wiki/Ernesto_Laclau)
LaclauGPT is developed by [Tomi Toivio](mailto:tomi.toivio@helsinki.fi) for the [Helsinki Hub on Emotions, Populism and Polarisation](https://www.helsinki.fi/en/researchgroups/emotions-populism-and-polarisation). 
LaclauGPT is a part of the Anarcho-Computational/Discourse-Analytical (AC/DT) Framework. 

## What does Anarcho-Computational/Discourse-Theoretical mean?
* Anarcho: We reject scientific dogmaticism in the spirit of Paul Feyerabend's epistemological anarchism. 
* Computational: Simon Lindgren inspired us to experiment with the methods of computational social science.  
* Discourse: We are heavy users of Ernesto Laclau's theory of discourse analysis.
* Theoretical: We use Manuel Castell's theory of Network Society and Social Network Analysis.

## Data Analysis
Data Analysis is performed in several steps.
The steps use different LLM models and other data analysis tools.
They also use different methods and theories.
* Multimodal Analysis - Data is processed using a multimodal LLM. 
* Discourse Analysis - Discourse analysis using Ernesto Laclau's theory. 
* Network Analysis - Social Network Analysis using Manuel Castells' Network Theory.

## Open Source LLMs
LaclauGPT uses Ollama to run open souce LLMs on CSC Puhti supercomputer.

## Distributed Computing
LaclauGPT is a distributed system with several modules. They communicate with:
* Celery for task queue.
* MongoDB for storing data. 
* S3 object storage for files. 
* Redis for configuration.
* FastAPI for API requests.
* NATS for LLM context.

## LaclauGPT Required Modules
These are the required modules of LaclauGPT.
* [LaclauGPT: Data Analysis](https://github.com/TomiToivio/LaclauGPT-Data-Analysis) 
* [LaclauGPT: Data Storage](https://github.com/TomiToivio/LaclauGPT-Data-Storage)
* [LaclauGPT: Data Collection](https://github.com/TomiToivio/LaclauGPT-Data-Collection)
* [LaclauGPT: Data Visualization](https://github.com/TomiToivio/LaclauGPT-Data-Visualization)

## LaclauGPT Optional Modules
These modules are experimental and optional.
* [LaclauGPT: Deep Research Agent](https://github.com/TomiToivio/LaclauGPT-Deep-Research-Agent)
* [LaclauGPT: Data Collection Agent](https://github.com/TomiToivio/LaclauGPT-Data-Collection-Agent)
* [LaclauGPT: Social Simulation Laboratory](https://github.com/TomiToivio/LaclauGPT-Social-Simulation-Laboratory)
* [LaclauGPT: Web Scraper](https://github.com/TomiToivio/LaclauGPT-Web-Scraper)
