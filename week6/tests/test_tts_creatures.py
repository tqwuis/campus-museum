"""Browser regression checks. Run with the TTS dependencies, Playwright and Chrome.

    python -m pip install playwright
    python tests/test_tts_creatures.py

The local server uses an available port. Synthetic WAV fixtures exercise timing
and failures; set TTS_TEST_REAL=1 to additionally check the installed Piper model.
"""
import io
import hashlib
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
import wave

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server, WSGIRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tts_app import app


def fixture_wav():
    """A long enough clip with a known silent interval for seek/pause checks."""
    output = io.BytesIO()
    rate = 16000
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(b"".join(
            struct.pack("<h", 0 if 2 <= i / rate < 4 else
                        int(10000 * math.sin(2 * math.pi * 220 * i / rate)))
            for i in range(rate * 10)
        ))
    return output.getvalue()


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


class ReadingFriendsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0, app, threaded=True,
                                 request_handler=QuietHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel="chrome", headless=True)
        cls.wav = fixture_wav()
        cls.artifacts = Path(tempfile.gettempdir()) / "campus-tts-check"
        cls.artifacts.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server_thread.join(timeout=5)
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/api/tts", lambda route: route.fulfill(
            status=200, content_type="audio/wav", body=self.wav,
            headers={"X-Processing-Ms": "12.3"}))
        self.page.goto(self.url + "/tts")
        self.page.wait_for_function("Boolean(window.creatureStage)")

    def tearDown(self):
        try:
            self.assertEqual(self.errors, [])
        finally:
            self.context.close()

    def generate(self, text="Hello, reading friends!"):
        self.page.locator("#text").fill(text)
        self.page.locator("#speak").click()
        expect(self.page.locator("#creature-stage")).to_have_attribute("data-state", "ready", timeout=60000)
        expect(self.page.locator("#audio")).to_be_visible()

    def play(self):
        self.page.locator("#audio").evaluate("audio => audio.play()")
        expect(self.page.locator("#creature-stage")).to_have_attribute("data-state", "speaking")

    def mouth(self, creature="mochi"):
        return self.page.locator(f'[data-creature="{creature}"] .creature-mouth')

    def test_input_picker_and_request_speaker_stay_in_sync(self):
        requests = []
        self.page.on("request", lambda request: requests.append(request.post_data_json)
                     if request.url.endswith("/api/tts") else None)
        self.assertEqual(self.page.locator("#tts-form .creature-choice").count(), 3)
        self.assertEqual(self.page.locator("#creature-stage #creature-random").count(), 0)
        for reader in ("mochi", "popo", "kongi"):
            choice = self.page.locator(f'.creature-choice[data-reader="{reader}"]')
            choice.focus()
            self.page.keyboard.press("Enter")
            expect(choice).to_have_attribute("aria-pressed", "true")
            expect(self.page.locator(f'[data-creature="{reader}"]')).to_have_attribute("aria-pressed", "true")
            self.generate()
            self.assertEqual(requests[-1]["creature"], reader)
            expect(self.page.locator("#creature-stage")).to_have_attribute("data-speaker", reader)
        self.page.locator('[data-creature="mochi"]').click(force=True)
        expect(self.page.locator('.creature-choice[data-reader="mochi"]')).to_have_attribute("aria-pressed", "true")
        # Lock a deterministic random choice and ensure the request uses that same snapshot.
        self.page.evaluate("Math.random = () => 0.51")
        self.page.locator("#creature-random").click()
        self.generate()
        self.assertEqual(requests[-1]["creature"], "popo")
        self.page.locator('.creature-choice[data-reader="kongi"]').click()
        self.play()
        expect(self.page.locator("#creature-stage")).to_have_attribute("data-speaker", "popo")
        expect(self.page.locator("#creature-bubble-name")).to_contain_text("포포")
        self.assertEqual(len(requests), 4)

    def test_snapshot_playback_silence_seek_replay_and_download(self):
        self.page.locator('[data-creature="mochi"]').click(force=True)
        self.generate("Hello <b>friends</b>!")
        expect(self.page.locator("#creature-bubble")).to_be_hidden()
        self.assertTrue(self.page.locator("#audio").evaluate("a => a.paused"))
        self.page.locator("#text").fill("A different sentence.")
        self.page.locator('[data-creature="popo"]').click(force=True)
        self.play()
        expect(self.page.locator("#creature-bubble-name")).to_contain_text("모찌")
        expect(self.page.locator("#creature-quote")).to_have_text("Hello <b>friends</b>!")
        self.assertEqual(self.page.locator("#creature-quote b").count(), 0)
        self.page.wait_for_function("Number(document.querySelector('[data-creature=mochi] .creature-mouth').getAttribute('ry')) > 2")
        self.page.locator("#audio").evaluate("a => a.pause()")
        expect(self.page.locator("#creature-stage")).to_have_attribute("data-state", "paused")
        self.assertLessEqual(float(self.mouth().get_attribute("ry")), 1.5)
        expect(self.page.locator("#creature-bubble")).to_be_visible()
        self.page.locator("#audio").evaluate("a => { a.currentTime = 2.3; }")
        self.play()
        self.page.wait_for_timeout(180)
        self.assertLessEqual(float(self.mouth().get_attribute("ry")), 1.5)
        self.page.locator("#audio").evaluate("a => { a.currentTime = 4.5; }")
        self.page.wait_for_function("Number(document.querySelector('[data-creature=mochi] .creature-mouth').getAttribute('ry')) > 2")
        self.page.locator("#audio").evaluate("a => { a.currentTime = a.duration - 0.1; }")
        expect(self.page.locator("#creature-bubble")).to_be_hidden()
        self.play()
        expect(self.page.locator("#creature-bubble-name")).to_contain_text("모찌")
        with self.page.expect_download() as download:
            self.page.locator("#wav-download").click()
        self.assertEqual(Path(download.value.path()).read_bytes(), self.wav)
        self.generate()
        self.play()
        expect(self.page.locator("#creature-bubble-name")).to_contain_text("포포")
        self.page.locator("#creature-random").click()
        expect(self.page.locator("#creature-random")).to_have_attribute("aria-pressed", "true")
        expect(self.page.locator("#creature-bubble-name")).to_contain_text("포포")
        self.page.screenshot(path=str(self.artifacts / "desktop.png"))

    def test_pending_request_failure_and_recovery(self):
        self.generate()
        self.play()
        self.page.unroute("**/api/tts")
        pending = []
        self.page.route("**/api/tts", lambda route: pending.append(route))
        self.page.locator("#speak").click()
        expect(self.page.locator("#creature-stage")).to_have_attribute("data-state", "generating")
        speaker = self.page.locator("#creature-stage").get_attribute("data-speaker")
        expect(self.page.locator("#creature-bubble")).to_be_hidden()
        self.assertTrue(self.page.locator("#audio").evaluate("a => a.paused"))
        expect(self.page.locator("#speak")).to_be_disabled()
        expect(self.page.locator('.creature-choice[data-reader="kongi"]')).to_be_disabled()
        self.page.locator('[data-creature="kongi"]').click(force=True)
        expect(self.page.locator("#creature-stage")).to_have_attribute("data-speaker", speaker)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].request.post_data_json["creature"], speaker)
        pending.pop().fulfill(status=503, content_type="application/json",
                              body='{"error":"Model temporarily unavailable"}')
        expect(self.page.locator("#tts-status")).to_contain_text("Model temporarily unavailable")
        expect(self.page.locator("#speak")).to_be_enabled()
        expect(self.page.locator(".creature-badge:visible")).to_have_count(0)
        self.page.unroute("**/api/tts")
        self.page.route("**/api/tts", lambda route: route.fulfill(
            content_type="audio/wav", body=self.wav))
        self.generate()
        self.play()
        expect(self.page.locator("#creature-bubble-name")).to_contain_text("콩이")

    def test_mobile_long_text_focus_and_reduced_motion(self):
        self.page.set_viewport_size({"width": 360, "height": 740})
        choice = self.page.locator('.creature-choice[data-reader="mochi"]')
        choice.click()
        expect(choice).to_have_attribute("aria-pressed", "true")
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.page.screenshot(path=str(self.artifacts / "mobile-picker.png"))
        text = ("Reading with our little friends is fun. " * 8)[:300]
        self.generate(text)
        self.page.locator("#audio").scroll_into_view_if_needed()
        self.play()
        self.page.wait_for_timeout(250)
        bubble = self.page.locator("#creature-bubble").bounding_box()
        audio = self.page.locator("#audio").bounding_box()
        self.assertGreaterEqual(bubble["x"], 0)
        self.assertLessEqual(bubble["x"] + bubble["width"], 360)
        self.assertLessEqual(bubble["height"], 144.5)
        self.assertLessEqual(audio["y"] + audio["height"], bubble["y"] + 1)
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        quote = self.page.locator("#creature-quote")
        expect(quote).to_have_text(text)
        self.assertTrue(quote.evaluate("e => e.scrollHeight > e.clientHeight"))
        quote.focus()
        self.page.keyboard.press("End")
        self.page.wait_for_function("document.querySelector('#creature-quote').scrollTop > 0")
        self.assertGreater(quote.evaluate("e => e.scrollTop"), 0)
        self.page.screenshot(path=str(self.artifacts / "mobile.png"))
        self.page.emulate_media(reduced_motion="reduce")
        positions = self.page.locator(".creature").evaluate_all("els => els.map(e => e.getBoundingClientRect().x)")
        self.page.wait_for_timeout(250)
        self.assertEqual(positions, self.page.locator(".creature").evaluate_all("els => els.map(e => e.getBoundingClientRect().x)"))
        for mouth in self.page.locator(".creature-mouth").all():
            self.assertLessEqual(float(mouth.get_attribute("ry")), 1.5)
        self.page.locator("#audio").evaluate("a => { a.pause(); a.currentTime = a.duration; }")
        self.page.evaluate("window.creatureStage.reset()")
        self.page.emulate_media(reduced_motion="no-preference")
        button = self.page.locator('[data-creature="kongi"]')
        button.focus()
        before = button.bounding_box()["x"]
        self.page.wait_for_timeout(400)
        self.assertEqual(before, button.bounding_box()["x"])
        self.page.keyboard.press("Enter")
        expect(button).to_have_attribute("aria-pressed", "true")
        self.page.reload()
        expect(self.page.locator("#creature-random")).to_have_attribute("aria-pressed", "true")

    @unittest.skipUnless(os.environ.get("TTS_TEST_REAL") == "1", "Set TTS_TEST_REAL=1 for real Piper")
    def test_real_piper_three_distinct_models(self):
        self.page.unroute("**/api/tts")
        self.page.set_default_timeout(60000)
        durations = []
        wav_hashes = set()
        sentence = "Hello! Welcome to our campus museum."
        for reader in ("mochi", "popo", "kongi"):
            self.page.locator(f'.creature-choice[data-reader="{reader}"]').click()
            with self.page.expect_response(lambda r: r.url.endswith("/api/tts")) as response_info:
                self.generate(sentence)
            response = response_info.value
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["x-tts-creature"], reader)
            self.assertIn("audio/wav", response.headers["content-type"])
            # Inspect the same WAV used for playback and download.
            wav_bytes = bytes(self.page.locator("#audio").evaluate("""async audio =>
                Array.from(new Uint8Array(await (await fetch(audio.src)).arrayBuffer()))
            """))
            wav_hashes.add(hashlib.sha256(wav_bytes).hexdigest())
            with wave.open(io.BytesIO(wav_bytes)) as wav:
                self.assertGreater(wav.getnframes(), 0)
                self.assertEqual(wav.getnchannels(), 1)
            (self.artifacts / f"voice-{reader}.wav").write_bytes(wav_bytes)
            durations.append(float(self.page.locator("#tts-duration").inner_text().removesuffix("초")))
            self.assertTrue(self.page.locator("#waveform").evaluate("c => c.width > 0 && c.height > 0"))
            self.play()
            expect(self.page.locator("#creature-quote")).to_have_text(sentence)
            expect(self.page.locator("#creature-bubble")).to_be_hidden(timeout=15000)
        self.assertTrue(all(duration > 0 for duration in durations))
        self.assertEqual(len(wav_hashes), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
