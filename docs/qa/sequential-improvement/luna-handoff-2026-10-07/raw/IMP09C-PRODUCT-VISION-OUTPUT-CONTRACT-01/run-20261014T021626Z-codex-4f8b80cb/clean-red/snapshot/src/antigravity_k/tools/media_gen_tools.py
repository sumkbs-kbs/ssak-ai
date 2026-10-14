import logging
import os
import shutil
import subprocess
from importlib import import_module
from typing import NotRequired, Protocol, TypedDict, cast, final, override

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .egress_policy import safe_urlopen

logger = logging.getLogger(__name__)
JsonMap = dict[str, object]


class _ParameterSpec(TypedDict):
    type: str
    description: str
    default: NotRequired[str]


class _ParametersSchema(TypedDict):
    type: str
    properties: dict[str, _ParameterSpec]
    required: list[str]


def _as_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def _download_asset(url: str, destination: str) -> None:
    with safe_urlopen(url, allow_local=False) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


class _SoundFileModule(Protocol):
    def write(self, file: str, data: object, samplerate: int) -> object: ...


class _Kokoro(Protocol):
    def create(self, text: str, *, voice: str, speed: float, lang: str) -> tuple[object, int]: ...


class _KokoroFactory(Protocol):
    def __call__(self, model_path: str, voices_path: str) -> _Kokoro: ...


@final
class GenerateImageTool(BaseTool):
    category: ToolCategory = ToolCategory.CUSTOM
    render_in: RenderIn = RenderIn.BACKGROUND
    risk_level: RiskLevel = RiskLevel.LOW
    icon: str = "🖼️"
    tags: list[str] = ["image", "generation", "mflux"]

    @property
    @override
    def name(self) -> str:
        return "generate_image"

    @property
    @override
    def description(self) -> str:
        return "Generate an image using the FLUX.1 model via MLX. Use this to create visual assets from a text prompt."

    @property
    @override
    def parameters_schema(self) -> _ParametersSchema:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A detailed description of the image to generate",
                },
                "output_path": {
                    "type": "string",
                    "description": "Absolute path where the output image should be saved (.png)",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio of the image (e.g., '1:1', '16:9', '9:16', '4:3', '3:4')",
                    "default": "1:1",
                },
            },
            "required": ["prompt", "output_path"],
        }

    @override
    def execute(self, **kwargs: object) -> str:
        prompt = _as_text(kwargs.get("prompt"))
        output_path = _as_text(kwargs.get("output_path"))
        aspect_ratio = _as_text(kwargs.get("aspect_ratio"), "1:1")
        dims = {
            "1:1": "1024x1024",
            "16:9": "1365x768",
            "9:16": "768x1365",
            "4:3": "1152x896",
            "3:4": "896x1152",
        }
        size = dims.get(aspect_ratio, "1024x1024")
        width, height = size.split("x")

        # mflux-generate uses FLUX.1-schnell by default, extremely fast on Apple Silicon
        cmd = [
            "mflux-generate",
            "--prompt",
            prompt,
            "--model",
            "schnell",
            "--steps",
            "4",
            "--width",
            width,
            "--height",
            height,
            "--output",
            output_path,
        ]

        try:
            _ = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return f"Image successfully generated at: {output_path}"
        except subprocess.CalledProcessError as e:
            return f"Failed to generate image. Error: {_as_text(cast(object, e.stderr))}"


@final
class GenerateAudioTool(BaseTool):
    category: ToolCategory = ToolCategory.CUSTOM
    render_in: RenderIn = RenderIn.BACKGROUND
    risk_level: RiskLevel = RiskLevel.LOW
    icon: str = "🎵"
    tags: list[str] = ["audio", "tts", "generation", "kokoro"]

    @property
    @override
    def name(self) -> str:
        return "generate_audio"

    @property
    @override
    def description(self) -> str:
        return "Generate audio (TTS) from text using the Kokoro model. Use this to create spoken audio assets (.wav)."

    @property
    @override
    def parameters_schema(self) -> _ParametersSchema:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to synthesize into speech",
                },
                "output_path": {
                    "type": "string",
                    "description": "Absolute path where the output audio should be saved (.wav)",
                },
                "voice": {
                    "type": "string",
                    "description": "Voice identifier (e.g., 'af_heart' for female, 'am_adam' for male)",
                    "default": "af_heart",
                },
            },
            "required": ["text", "output_path"],
        }

    @override
    def execute(self, **kwargs: object) -> str:
        text = _as_text(kwargs.get("text"))
        output_path = _as_text(kwargs.get("output_path"))
        voice = _as_text(kwargs.get("voice"), "af_heart")
        try:
            sf = cast(_SoundFileModule, cast(object, import_module("soundfile")))
            kokoro_factory = cast(_KokoroFactory, import_module("kokoro_onnx").__dict__["Kokoro"])

            model_path = os.path.join(os.getcwd(), "data", "kokoro-v0_19.onnx")
            voices_path = os.path.join(os.getcwd(), "data", "voices.json")

            os.makedirs(os.path.dirname(model_path), exist_ok=True)

            if not os.path.exists(model_path):
                print(f"Downloading Kokoro ONNX model to {model_path}...")
                _download_asset(
                    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx",
                    model_path,
                )
            if not os.path.exists(voices_path):
                print(f"Downloading Kokoro voices to {voices_path}...")
                _download_asset(
                    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.json",
                    voices_path,
                )

            kokoro = kokoro_factory(model_path, voices_path)
            # Default to US English, could parameterize language mapping later
            samples, sample_rate = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")

            _ = sf.write(output_path, samples, sample_rate)
            return f"Audio successfully generated at: {output_path}"
        except ImportError:
            return "Failed to generate audio: kokoro-onnx or soundfile is not installed."
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Failed to generate audio: {_as_text(e)}"


@final
class GenerateVideoTool(BaseTool):
    category: ToolCategory = ToolCategory.CUSTOM
    render_in: RenderIn = RenderIn.BACKGROUND
    risk_level: RiskLevel = RiskLevel.LOW
    icon: str = "🎬"
    tags: list[str] = ["video", "generation", "ltx"]

    @property
    @override
    def name(self) -> str:
        return "generate_video"

    @property
    @override
    def description(self) -> str:
        return "Generate a short video from text using a local Video Generation model (LTX-Video). This takes several minutes."  # noqa: E501

    @property
    @override
    def parameters_schema(self) -> _ParametersSchema:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A detailed description of the video to generate",
                },
                "output_path": {
                    "type": "string",
                    "description": "Absolute path where the output video should be saved (.mp4)",
                },
            },
            "required": ["prompt", "output_path"],
        }

    @override
    def execute(self, **kwargs: object) -> str:
        prompt = _as_text(kwargs.get("prompt"))
        output_path = _as_text(kwargs.get("output_path"))
        script_content = f"""import torch
from diffusers import LTXPipeline
from diffusers.utils import export_to_video
import os
import sys

try:
    print("Loading LTX-Video pipeline on MPS...")
    pipe = LTXPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.float16)
    pipe.to("mps")
    print("Generating video...")
    video = pipe(prompt="{prompt}", num_frames=33, num_inference_steps=20).frames[0]
    export_to_video(video, "{output_path}", fps=8)
    print("Export complete.")
except Exception as e:
    with open("video_error.log", "w") as f:
        f.write(str(e))
    sys.exit(1)
"""
        script_path = os.path.join(os.getcwd(), "temp_gen_video.py")
        with open(script_path, "w") as f:
            _ = f.write(script_content)

        try:
            # We run this as a subprocess to keep the tool memory isolated and allow it to fail cleanly
            _ = subprocess.run(["python", script_path], check=True, capture_output=True, text=True)
            if os.path.exists(script_path):
                os.remove(script_path)
            return f"Video successfully generated at: {output_path}"
        except subprocess.CalledProcessError as e:
            error = _as_text(cast(object, e.stderr))
            if os.path.exists("video_error.log"):
                with open("video_error.log", "r") as f:
                    error = f.read()
            return f"Failed to generate video: {error}"
