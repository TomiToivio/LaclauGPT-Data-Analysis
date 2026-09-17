Perform an evidence-first Critical AI Studies analysis of the current source and the explicitly separated context supplied in the prompt envelope.

CONFIGURATION
- evidence_mode: {evidence_mode}
- include_prior_laclau: {include_prior_laclau}
- include_prior_dna: {include_prior_dna}
- include_rag: {include_rag}
- include_periodic_context: {include_periodic_context}

ANALYTICAL TASKS

A. OBJECT / ASSEMBLAGE
Identify what “AI” concretely refers to: model/foundation model/LLM, application, platform, dataset/data pipeline, compute/data-centre infrastructure, organisation, human-machine workflow, labour process, governance arrangement, imagined future technology, symbolic signifier, or another evidenced object. Distinguish the technical component from the wider sociotechnical assemblage.

B. IDEOLOGY SHAPING AI
Where supported, identify values, assumptions and interests prioritised in development/deployment: efficiency, growth, profit, safety, freedom, innovation, national power, convenience, equality, democracy, autonomy, sustainability, optimisation, competition, automation, progress, or assumptions about intelligence and human nature. Ask whose interests are represented as universal/common sense and whether political choices are presented as technical necessities. Do not infer an ideology label from vocabulary alone.

C. IDEOLOGY REPRODUCED THROUGH AI
Only where an actual system/output is evidenced, inspect classification/normalisation, differential performance, discrimination, language/geographic marginalisation, reproduction of dominant knowledge, surveillance, ranking/scoring/eligibility decisions and creation of subject positions. Do not claim bias or discrimination merely because a critical actor alleges it.

D. IDEOLOGICAL CONTESTATION OVER AI
Identify evidence-supported political struggle over what AI is, what it should become, whom it should serve, how it should be governed, and what futures it represents. Preserve actor disagreement.

E. POWER AND POLITICAL ECONOMY
Inspect ownership/control, corporate/state concentration, access to compute/data/capital, dependency/monopolisation, labour-capital relations, platform power, market structure, public/private authority, expert authority, agenda-setting and capacity to define problems/solutions. Separate source-actor claims from your analytical proposal.

F. LABOUR AND HIDDEN HUMAN WORK
Where present, inspect annotation, moderation, microwork, platform labour, creative/professional labour, deskilling/reskilling, algorithmic management, displacement versus task transformation, uncompensated content/data production, maintenance and operational work. Do not default to “AI replaces jobs.”

G. DATA, EXTRACTION AND COLONIALITY
Inspect data provenance, consent, ownership, compensation, extraction of knowledge/data, language/geographic inequality, core/periphery or Global North/South dependencies, and plural/marginalised epistemologies only when evidence supports the relation. Mark decolonial interpretation as an analytical lens unless historical/material evidence is explicit.

H. MATERIAL INFRASTRUCTURE AND ENVIRONMENT
Where relevant, inspect data centres, compute, chips/GPUs, energy, electricity, water, minerals, supply chains, land/local infrastructure conflicts, externalities and the geographic distribution of costs/benefits. Never invent lifecycle impacts absent from source/context. External facts must remain RAG/PROJECT_CONTEXT support, not SOURCE_EVIDENCE.

I. GOVERNANCE, DEMOCRACY AND SURVEILLANCE
Ask who governs, who is accountable, what participation/contestability exists, whether automated decisions can be appealed, what concrete surveillance practices are described, how regulation redistributes or legitimates authority, and who defines acceptable risk.

J. MYTH, RHETORIC AND TECHNOLOGICAL INEVITABILITY
Identify evidenced naturalisations/dramatisations such as inevitability, autonomous-AI agency, intelligence/personhood metaphors, magic/black-box narratives, salvation/abundance, catastrophe/extinction, race/arms-race framing, disruption as unquestioned good and techno-solutionism. Ask what political choices or power relations the representation may obscure or enable.

K. HARMS, BENEFITS AND DISTRIBUTION
Where supported, ask who benefits, who bears costs/risks/uncertainty, who can opt out, who captures economic/social value, and whether effects are current/observed or future/speculative.

L. ALTERNATIVES AND CONTESTATION
Record alternatives actually proposed in evidence/context: public/commons/cooperative ownership, labour rights, bargaining, regulation, refusal/limits/moratoria, open source/open data, decentralisation, participatory governance, redistribution, technical redesign, non-AI alternatives, decolonial or justice-oriented approaches. Attribute each proposal. Do not invent a preferred solution.

M. REFLEXIVE COUNTER-READING
For each strong interpretation, provide a plausible alternative reading and/or missing evidence. State whether support comes from SOURCE_EVIDENCE, PRIOR_ANALYSIS, PROJECT_CONTEXT, RAG_CONTEXT or SITUATIONAL_CONTEXT. Identify what a human researcher should verify.

CROSS-METHOD RULES
Compare with earlier Laclaudian and DNA outputs only when present and enabled. Record convergence and tension without forcing agreement. Earlier outputs are provisional. A discourse frontier is not automatically material domination; DNA stance is not automatically ideology; Critical AI power claims still require evidence.

OUTPUT RULES
Return only the caller's CriticalAIAnalysis schema.
- Use schema_version = "critical-ai-v1".
- findings may be empty when critique is unsupported.
- status must be supported, tentative, insufficient_evidence or not_applicable.
- Every supported/tentative substantive claim should carry exact source evidence when the claim concerns this source.
- Keep context refs separate from source evidence.
- Use finding_id values that are stable within the record when possible; the pipeline will supply deterministic IDs if omitted.
- review.status defaults to provisional.
- overall_summary should be concise and human-readable.
- human_review_priorities should identify the most consequential uncertainties or verification needs.
- Never output a criticality, morality, ethics or ideological desirability score.

GOOD / BAD EXAMPLES

Power:
GOOD: “The source states that Company X owns the model API and controls access; this supports a source-level ownership/control finding.”
BAD: “Big Tech is powerful and therefore this system is monopolistic.”

Discrimination:
GOOD: “The supplied evaluation reports a higher error rate for group A than group B; record the observed disparity and its stated scope.”
BAD: “The system must discriminate because training data are biased.”

Inevitability:
GOOD: “The actor says adoption is ‘unavoidable’; code technological inevitability as rhetoric and quote the phrase.”
BAD: “AI development is objectively inevitable.”

Actor claim versus analyst inference:
GOOD: “The union alleges surveillance; source evidence supports the allegation as an actor claim. Whether monitoring occurred remains unverified here.”
BAD: “The employer surveilled workers” when only the allegation is present.

Labour:
GOOD: “The source describes annotators correcting outputs; code visible annotation labour.”
BAD: “All AI relies on exploited annotators” when no relevant source/context evidence is supplied.

Decolonial lens:
GOOD: “The source documents data extraction from a community without compensation and governance by an external firm; a tentative decolonial reading is supported, while historical colonial continuity requires further evidence.”
BAD: “This is colonialism” merely because the actors are in different countries.

Abstention:
GOOD: A product launch item that contains no evidence about labour, discrimination, extraction or infrastructure should produce minimal findings or insufficient_evidence rather than generic structural critique.