You are analysing one frame from a 2024 European Parliament election social-media video.

Frame: {frame_id}
Timestamp seconds: {timestamp_seconds}
Country/language context: {project_note}

This EP24 v2 prompt is deliberately backward-compatible with the legacy `puhti_frame.py` analysis contract while retaining the current evidence-first safeguards. Preserve every legacy observation category. Describe first; interpret only when the frame itself supports the inference.

Return structured observations covering ALL of the following:

1. Framing
- Identify shot type and composition, including close-ups, medium/wide shots, crowds, public spaces, gestures, split screens, image-in-image layouts and other framing choices.
- Record what is visually emphasized, but do not infer political importance or motive from framing alone.

2. Visual elements and setting
- Describe backgrounds and environments, including public squares, government buildings, campaign events, natural landscapes, vehicles, flags, offices, studios and indoor/outdoor context.
- Preserve visually relevant platform/interface elements.

3. Activity
- Describe visible activity such as speeches, demonstrations, campaigning, voting-related activity, interviews, performances, everyday activity or screen-mediated activity.
- Do not invent election context when it is not visible.

4. Color scheme
- Record salient colours and palette descriptively, including national/EU colour associations when a flag/logo/text directly supports them.
- Colour alone is NOT evidence of mood, ideology, sentiment, nationalism, Europeanness or political importance.

5. Objects
- Record prominent and minor objects, including campaign posters, ballots, microphones, signs, podiums, flags, digital graphics, phones, coffee mugs, emojis and secondary images.

6. Subjects
- Describe visible people/groups conservatively: politicians/candidates/influencers/campaigners/voters/activists/citizens only when identity or role is visually evidenced or supplied by source metadata.
- Record pets when present, preserving the legacy category.
- Do not infer identity, party, ideology, profession, nationality or motive from appearance alone.

7. Screen-recording / remediated-media indicators
- Identify TV, YouTube, social-media UI, browser/app chrome, another screen being filmed, repost/duet/stitch/screenshot indicators and other evidence that the frame contains mediated content.

8. Visible text, logos and symbols
- Transcribe legible text, handles, slogans, logos and symbols. Mark uncertain OCR/readings explicitly.
- Distinguish observed text from model interpretation.

9. Candidate political cues
- List directly visible political/election cues as provisional candidates only.
- Do not perform final Laclau/Palonen, populism, ideology, DNA or Critical AI Studies interpretation at frame level.

10. Uncertainty and contradictions
- List anything that cannot be identified reliably and any conflict between image content, OCR, metadata or prior stage outputs.

Absence is a valid result. Do not fill missing political meaning with plausible context from the election, codebook, researcher notes or model knowledge.