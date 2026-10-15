"""Voice routing regressions without loading Piper models or synthesizing speech.

    python -m unittest discover -s tests -p test_tts_voices.py -v
"""
import io
from pathlib import Path
import sys
import tempfile
from threading import Lock
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tts_app


class FakeVoice:
    def __init__(self):
        self.synthesize_wav = Mock(side_effect=self.write_wav)

    @staticmethod
    def write_wav(text, wav_file, *, syn_config):
        wav_file.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav_file.writeframes(b"\x00\x00" * 160)


class VoiceRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="tts-voices-")
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        self.models = {}
        for creature in ("mochi", "popo", "kongi"):
            model = directory / f"{creature}.onnx"
            model.write_bytes(b"fake model")
            Path(str(model) + ".json").write_text("{}", encoding="utf-8")
            self.models[creature] = model

        self.loaded = {}
        self.load = Mock(side_effect=self.load_voice)
        fake_piper = ModuleType("piper")
        fake_piper.PiperVoice = SimpleNamespace(load=self.load)
        fake_piper.SynthesisConfig = SimpleNamespace
        self.lock = Lock()
        for patcher in (
            patch.object(tts_app, "MODELS", self.models),
            patch.object(tts_app, "voices", {}),
            patch.object(tts_app, "voice_lock", self.lock),
            patch.dict(sys.modules, {"piper": fake_piper}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = tts_app.app.test_client()

    def load_voice(self, model_path):
        voice = FakeVoice()
        self.loaded[model_path] = voice
        return voice

    def request_voice(self, **overrides):
        return self.client.post("/api/tts", json={
            "text": "Hello, reading friends!", "length_scale": 1.0, **overrides,
        })

    def assert_wav(self, response, creature):
        self.assertEqual(response.status_code, 200, response.get_data(as_text=False))
        self.assertEqual(response.mimetype, "audio/wav")
        self.assertEqual(response.headers["X-TTS-Creature"], creature)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        with wave.open(io.BytesIO(response.data), "rb") as wav_file:
            self.assertEqual(wav_file.getnframes(), 160)
            self.assertEqual(wav_file.getframerate(), 16000)

    def test_default_and_explicit_creatures_use_distinct_cached_models(self):
        self.assert_wav(self.request_voice(), "mochi")
        for creature in self.models:
            with self.subTest(creature=creature):
                self.assert_wav(self.request_voice(
                    creature=creature, text="  A second sentence.  ", length_scale=1.25,
                ), creature)
                self.assert_wav(self.request_voice(creature=creature), creature)
                voice = self.loaded[str(self.models[creature])]
                submitted = voice.synthesize_wav.call_args_list[-2]
                self.assertEqual(submitted.args[0], "A second sentence.")
                self.assertEqual(submitted.kwargs["syn_config"].length_scale, 1.25)
        self.assertEqual([call.args[0] for call in self.load.call_args_list],
                         [str(model) for model in self.models.values()])
        self.assertEqual(set(tts_app.voices), set(self.models))

    def test_invalid_creatures_are_rejected_before_loading(self):
        for creature in ("../models/other.onnx", str(self.models["mochi"]),
                         "unknown", "", [], {}, None, 1, True):
            with self.subTest(creature=creature):
                response = self.request_voice(creature=creature)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())
        self.load.assert_not_called()

    def test_missing_selected_model_or_config_does_not_fall_back(self):
        self.assert_wav(self.request_voice(), "mochi")
        for suffix in ("", ".json"):
            with self.subTest(missing_suffix=suffix):
                missing = Path(str(self.models["popo"]) + suffix)
                contents = missing.read_bytes()
                missing.unlink()
                try:
                    response = self.request_voice(creature="popo")
                    self.assertEqual(response.status_code, 503)
                    self.assertIn(tts_app.CREATURE_NAMES["popo"],
                                  response.get_json()["error"])
                    self.assertNotIn("popo", tts_app.voices)
                    self.assertEqual(self.load.call_count, 1)
                finally:
                    missing.write_bytes(contents)
        self.assert_wav(self.request_voice(creature="popo"), "popo")

    def test_failed_model_load_is_not_cached_and_can_be_retried(self):
        self.load.side_effect = RuntimeError("unreadable model")
        with self.assertLogs(tts_app.app.logger, level="ERROR"):
            response = self.request_voice(creature="kongi")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("kongi", tts_app.voices)
        self.assertFalse(self.lock.locked())
        self.load.side_effect = self.load_voice
        self.assert_wav(self.request_voice(creature="kongi"), "kongi")
        self.assertEqual(self.load.call_count, 2)

    def test_busy_request_is_rejected_and_next_request_succeeds(self):
        self.lock.acquire()
        try:
            response = self.request_voice(creature="popo")
            self.assertEqual(response.status_code, 429)
            self.assertIn("error", response.get_json())
            self.load.assert_not_called()
            self.assertTrue(self.lock.locked())
        finally:
            self.lock.release()
        self.assert_wav(self.request_voice(creature="popo"), "popo")

    def test_synthesis_failure_releases_lock_for_other_voice(self):
        self.assert_wav(self.request_voice(creature="popo"), "popo")
        voice = self.loaded[str(self.models["popo"])]

        def fail_synthesis(text, wav_file, *, syn_config):
            # Set a valid header so wave.close does not mask the intended error.
            wav_file.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            raise RuntimeError("synthesis failed")

        voice.synthesize_wav.side_effect = fail_synthesis
        with self.assertLogs(tts_app.app.logger, level="ERROR"):
            response = self.request_voice(creature="popo")
        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.lock.locked())
        self.assert_wav(self.request_voice(creature="kongi"), "kongi")
        voice.synthesize_wav.side_effect = voice.write_wav
        self.assert_wav(self.request_voice(creature="popo"), "popo")
        self.assertEqual(self.load.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
