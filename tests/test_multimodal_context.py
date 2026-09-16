from __future__ import annotations

from types import SimpleNamespace

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMCallProvenance,
    LLMResponse,
)
from laclaugpt_data_analysis.llm.multimodal import FrameAwareProvider


class FakeProvider:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content="{}",
            provenance=LLMCallProvenance(
                requested_mode="test",
                requested_model=request.model,
                resolved_model=request.model,
                actual_mode="test",
                actual_model=request.model,
            ),
        )


def test_local_frame_pixels_are_attached_and_audited(tmp_path) -> None:
    image = tmp_path / "frame-1.png"
    image.write_bytes(b"synthetic-frame")
    fake = FakeProvider()
    provider = FrameAwareProvider(
        fake,
        [SimpleNamespace(id="frame-1", media_ref=str(image))],
    )

    provider.chat(
        ChatRequest(
            model="fake",
            system="system",
            user="Analyse frame frame-1 at 1.0 seconds.",
        )
    )

    assert fake.requests[0].images == (str(image),)
    audit = provider.audit()
    assert audit["declared"] == "direct_image_pixels"
    assert audit["attachments"][0]["frame_id"] == "frame-1"
    assert audit["attachments"][0]["media_ref"] == str(image)


def test_remote_frame_reference_is_not_falsely_claimed_as_direct_pixels() -> None:
    fake = FakeProvider()
    provider = FrameAwareProvider(
        fake,
        [SimpleNamespace(id="frame-2", media_ref="s3://private-bucket/frame-2.png")],
    )

    provider.chat(
        ChatRequest(
            model="fake",
            system="system",
            user="Analyse frame frame-2 at 2.0 seconds.",
        )
    )

    assert fake.requests[0].images == ()
    audit = provider.audit()
    assert audit["declared"] == "textual_derivatives_only"
    assert audit["attachments"] == []
