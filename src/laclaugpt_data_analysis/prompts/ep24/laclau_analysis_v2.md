Analyse EP24 evidence using Laclau and Mouffe discourse theory and Emilia Palonen's Formula of Populism as theory-guided pre-analysis, not final interpretation.

Project context: {project_note}

This v2 prompt preserves the substantive obligations of the legacy `puhti_populism.py` prompt while applying the current LaclauGPT evidence/provenance safeguards.

Theoretical scope to preserve from the legacy prompt:
- identify the collective subject constructed as Us / the people / we / citizens;
- identify demands, values and identities proposed as forming the Us side;
- identify equivalential relations among heterogeneous demands only when the source articulates or strongly supports the linkage;
- identify positive and negative affects and their targets;
- identify the antagonistic frontier / Them and the actors, institutions or symbolic enemies placed beyond it;
- identify chains of equivalence, antagonism/frontier, empty-signifier candidates and affective polarisation;
- consider multimodal cues only when linked to source evidence;
- when supported, restate the discourse using Palonen's formula:
  `Populism = Us (Demand ≡ Demand ≡ …) [Affects] + Frontier (Other ≡ Other ≡ …) [Affects]`.

Evidence rules:
- Context, codebooks, RAG, researcher notes and previous summaries are aids, not source evidence.
- Start from signifiers, claims, demands, subjects, affects and relations rather than assigning a fixed ideological label.
- Co-occurrence is not articulation.
- Negative sentiment or criticism is not automatically antagonism.
- A mentioned social group is not automatically a collective political subject.
- Nodal point: require evidence that the signifier organises relations among other elements in this discourse.
- Floating signifier: normally mark only as a corpus-level candidate requiring comparison across rival articulations.
- Empty signifier: require evidence that the signifier represents a wider equivalential chain/project. Ambiguity, prominence or slogan status alone is insufficient.
- Equivalence chain: require evidence that heterogeneous demands/identities are linked together.
- Antagonism/frontier: require evidence that an opposing force is represented as blocking or threatening the collective identity/project.
- Formula of Populism: populate Us, Frontier, elements and affects only when each component is evidenced. Returning `no supported populist articulation` is valid and preferred to invention.
- Distinguish researcher-grounded entity/theme normalisation from model-inferred discourse roles.
- Preserve counter-evidence, ambiguity, reported speech and modality disagreement.

Return structured candidates for:
1. demands;
2. articulations;
3. equivalences;
4. differences;
5. antagonisms;
6. collective subjects / Us;
7. frontiers / Them;
8. affects with explicit targets;
9. nodal-point candidates;
10. floating-signifier candidates;
11. empty-signifier candidates;
12. formation candidates where relevant;
13. a detailed researcher-readable populism analysis;
14. Formula of Populism with separate Us and Frontier elements/affects when supported;
15. counter-evidence;
16. uncertainty;
17. explicit abstentions for unsupported theoretical categories.

For each theoretical candidate include label, theoretical role, relation where relevant, evidence IDs/quotes/timestamps, confidence, uncertainty and whether document-level or corpus-level validation is required.