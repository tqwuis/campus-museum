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
import re
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
        button.click(force=True)
        expect(button).to_have_attribute("aria-pressed", "true")
        self.page.reload()
        expect(self.page.locator("#creature-random")).to_have_attribute("aria-pressed", "true")

    def creature(self, name):
        return self.page.locator(f'[data-creature="{name}"]')

    def look(self, name):
        return tuple(float(self.creature(name).evaluate(
            f"e => e.style.getPropertyValue('--look-{axis}')").removesuffix("px") or 0) for axis in "xy")

    def eye_center(self, name):
        return self.creature(name).locator(".creature-eyes").evaluate(
            "e => { const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }")

    def positions(self):
        return self.page.locator(".creature").evaluate_all(
            "els => els.map(e => e.getBoundingClientRect().x)")

    def grab(self, name):
        # Press on a visible part of this friend even when another one overlaps it.
        x, y = self.creature(name).evaluate("""el => {
            const r = el.getBoundingClientRect();
            const y = r.y + r.height / 2;
            for (let i = 0; i <= 20; i++) {
                const x = r.x + r.width / 2 + (i % 2 ? 1 : -1) * Math.ceil(i / 2) * r.width / 22;
                if (document.elementFromPoint(x, y)?.closest('.creature') === el) return [x, y];
            }
            return [r.x + r.width / 2, y];
        }""")
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        return x, y

    def test_petting_reactions_and_saved_affection(self):
        mochi = self.creature("mochi")
        mochi.click(force=True)
        expect(mochi).to_have_attribute("aria-pressed", "true")
        expect(mochi.locator(".creature-chat")).to_be_visible()
        expect(mochi.locator(".creature-emote")).to_have_count(1)
        expect(mochi.locator(".creature-pose")).to_have_class(re.compile("react-hop"))
        # The third tap within 1.5 seconds becomes the excited reaction.
        mochi.click(force=True)
        mochi.click(force=True)
        expect(mochi.locator(".creature-pose")).to_have_class(re.compile("react-excited"))
        expect(mochi.locator(".creature-chat")).to_have_text("와아, 신난다!")
        mochi.click(force=True)
        mochi.click(force=True)
        expect(mochi.locator(".creature-hearts")).to_have_text("♥")
        expect(mochi).to_have_attribute("aria-label", re.compile("모찌, 민트색 젤리.*친밀도 하트 1개"))
        expect(self.page.locator("#creature-status")).to_contain_text("모찌와 더 친해졌어요")
        expect(mochi.locator(".creature-emote")).to_have_count(0, timeout=3000)
        expect(mochi.locator(".creature-chat")).to_be_hidden(timeout=3000)
        self.page.reload()
        expect(self.creature("mochi").locator(".creature-hearts")).to_have_text("♥")
        self.assertEqual(self.page.evaluate(
            "JSON.parse(localStorage.getItem('campus-tts-affection')).mochi"), 5)
        # Values of the wrong type or a broken document fall back to zero.
        self.page.evaluate("""localStorage.setItem('campus-tts-affection',
            JSON.stringify({mochi: "9", popo: -4, kongi: 1.5}))""")
        self.page.reload()
        expect(self.page.locator(".creature-hearts")).to_have_text(["", "", ""])
        self.page.evaluate("localStorage.setItem('campus-tts-affection', '{broken')")
        self.page.reload()
        self.creature("kongi").click(force=True)
        self.assertEqual(self.page.evaluate(
            "JSON.parse(localStorage.getItem('campus-tts-affection'))"),
            {"mochi": 0, "popo": 0, "kongi": 1})

    def test_affection_merges_across_tabs(self):
        other = self.context.new_page()
        other.goto(self.url + "/tts")
        other.wait_for_function("Boolean(window.creatureStage)")
        for _ in range(5):
            self.creature("mochi").click(force=True)
        expect(other.locator('[data-creature="mochi"] .creature-hearts')).to_have_text("♥")
        other.locator('[data-creature="popo"]').click(force=True)
        self.assertEqual(self.page.evaluate(
            "JSON.parse(localStorage.getItem('campus-tts-affection'))"),
            {"mochi": 5, "popo": 1, "kongi": 0})

    def test_blocked_storage_still_allows_petting(self):
        self.page.add_init_script("""Object.defineProperty(window, 'localStorage', {
            get() { throw new DOMException('blocked', 'SecurityError'); }
        });""")
        self.page.reload()
        self.page.wait_for_function("Boolean(window.creatureStage)")
        popo = self.creature("popo")
        for _ in range(5):
            popo.click(force=True)
        expect(popo.locator(".creature-hearts")).to_have_text("♥")
        expect(popo).to_have_attribute("aria-pressed", "true")

    def test_drag_reaches_across_the_field_without_selecting(self):
        popo = self.creature("popo")
        field = self.page.locator("#creature-field").bounding_box()
        x, y = self.grab("popo")
        self.page.mouse.move(x + 30, y, steps=5)
        expect(popo).to_have_class(re.compile("is-dragging"))
        # The old lane ended at two thirds of the field; every friend may now go past it.
        self.page.mouse.move(field["x"] + field["width"] * 0.8, y, steps=10)
        self.page.mouse.up()
        expect(popo).not_to_have_class(re.compile("is-dragging"))
        end = popo.bounding_box()
        self.assertGreater(end["x"] + end["width"], field["x"] + field["width"] * 2 / 3 + 20)
        self.assertLessEqual(end["x"] + end["width"], field["x"] + field["width"])
        expect(popo).to_have_attribute("aria-pressed", "false")
        expect(self.page.locator("#creature-random")).to_have_attribute("aria-pressed", "true")
        expect(popo.locator(".creature-emote")).to_have_count(0)
        # A second finger on another friend leaves the first drag in charge.
        x, y = self.grab("mochi")
        self.page.mouse.move(x + 20, y, steps=4)
        expect(self.creature("mochi")).to_have_class(re.compile("is-dragging"))
        popo.dispatch_event("pointerdown", {"pointerId": 99, "button": 0, "bubbles": True})
        popo.dispatch_event("pointermove", {"pointerId": 99, "clientX": 900, "bubbles": True})
        self.page.mouse.up()
        expect(self.creature("mochi")).not_to_have_class(re.compile("is-dragging"))
        expect(popo).not_to_have_class(re.compile("is-dragging"))
        # A cancelled drag ends the lift, and the next tap still selects.
        self.page.evaluate("addEventListener('pointerdown', e => { window.lastPointer = e.pointerId; }, true)")
        x, y = self.grab("popo")
        self.page.mouse.move(x - 20, y, steps=4)
        expect(popo).to_have_class(re.compile("is-dragging"))
        popo.dispatch_event("pointercancel", {
            "pointerId": self.page.evaluate("window.lastPointer"), "bubbles": True})
        expect(popo).not_to_have_class(re.compile("is-dragging"))
        self.page.mouse.up()
        popo.click(force=True)
        expect(popo).to_have_attribute("aria-pressed", "true")

    def test_friends_ignore_the_keyboard(self):
        for _ in range(25):
            self.page.keyboard.press("Tab")
            self.assertFalse(self.page.evaluate(
                "document.activeElement.classList.contains('creature')"))
        self.page.evaluate("document.activeElement.blur()")
        kongi = self.creature("kongi")
        expect(kongi).to_have_attribute("tabindex", "-1")
        kongi.click(force=True)
        expect(kongi).to_have_attribute("aria-pressed", "true")
        self.assertFalse(kongi.evaluate("b => b === document.activeElement"))
        before = kongi.bounding_box()["x"]
        for key in ("Enter", " ", "ArrowLeft", "ArrowRight"):
            self.page.keyboard.press(key)
        self.assertEqual(kongi.bounding_box()["x"], before)
        self.assertEqual(self.page.evaluate(
            "JSON.parse(localStorage.getItem('campus-tts-affection')).kongi"), 1)

    def test_drag_changes_expression(self):
        popo = self.creature("popo")
        lifted = popo.locator(".creature-face-lifted")
        dizzy = popo.locator(".creature-face-swinging")
        expect(popo.locator(".creature-drag-face")).to_be_hidden()
        x, y = self.grab("popo")
        for step in range(1, 5):
            self.page.mouse.move(x + step * 4, y)
            self.page.wait_for_timeout(40)
        expect(popo).to_have_class(re.compile("is-dragging"))
        expect(popo).not_to_have_class(re.compile("is-swinging"), timeout=2000)
        expect(lifted).to_be_visible()
        expect(dizzy).to_be_hidden()
        expect(popo.locator(".creature-eyes")).to_be_hidden()
        expect(popo.locator(".creature-mouth")).to_be_hidden()
        # A fast shake turns dizzy, then settles back once the pointer stops.
        self.page.mouse.move(x - 150, y, steps=5)
        expect(popo).to_have_class(re.compile("is-swinging"))
        expect(dizzy).to_be_visible()
        expect(lifted).to_be_hidden()
        expect(popo).not_to_have_class(re.compile("is-swinging"), timeout=2000)
        expect(lifted).to_be_visible()
        self.page.mouse.move(x + 100, y, steps=5)
        expect(popo).to_have_class(re.compile("is-swinging"))
        self.page.mouse.up()
        expect(popo).not_to_have_class(re.compile("is-(dragging|swinging)"))
        expect(popo.locator(".creature-drag-face")).to_be_hidden()
        expect(popo.locator(".creature-eyes")).to_be_visible()

    def use_virtual_time(self):
        # Fixed random numbers and a virtual clock make wandering repeatable.
        self.page.add_init_script("""(() => {
            let seed = 7;
            Math.random = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
        })();""")
        self.page.clock.install()
        self.page.reload()
        self.page.wait_for_function("Boolean(window.creatureStage)")
        self.page.locator("#creature-stage").evaluate("s => { s.dataset.sleepAfter = '99999999'; }")

    def test_friend_escapes_a_crowded_reader(self):
        self.use_virtual_time()
        mochi, popo = self.creature("mochi"), self.creature("popo")
        spot = mochi.bounding_box()
        x, y = self.grab("popo")
        self.page.mouse.move(spot["x"] + spot["width"] / 2, y, steps=8)
        self.page.mouse.up()
        # Popo now holds still on top of Mochi, which is pinned against the left edge.
        self.page.locator('.creature-choice[data-reader="popo"]').click()
        self.page.evaluate("window.creatureStage.begin('Hold still')")
        self.page.mouse.move(640, 5)
        self.page.clock.run_for(20000)
        apart = abs(mochi.bounding_box()["x"] - popo.bounding_box()["x"])
        self.assertGreaterEqual(apart, spot["width"] - 1)
        self.page.evaluate("window.creatureStage.reset()")

    def test_friends_spread_out_after_crowding(self):
        self.use_virtual_time()
        stage = self.page.locator("#creature-stage")
        # Every virtual second runs ~60 frames, so sample longest where space is tightest.
        for viewport, samples in (({"width": 1280, "height": 900}, 5), ({"width": 360, "height": 740}, 20)):
            self.page.set_viewport_size(viewport)
            self.page.clock.run_for(100)
            stage.evaluate("s => { s.dataset.sleepAfter = '99999999'; }")
            width = self.creature("mochi").bounding_box()["width"]
            spot = self.creature("mochi").bounding_box()
            for name in ("popo", "kongi"):
                x, y = self.grab(name)
                self.page.mouse.move(spot["x"] + spot["width"] / 2, y, steps=8)
                self.page.mouse.up()
            xs = self.positions()
            self.assertLess(max(xs) - min(xs), width, viewport)
            self.page.mouse.move(viewport["width"] / 2, 5)
            self.page.clock.run_for(30000)
            # Once spread out, wandering never brings two friends on top of each other.
            for _ in range(samples):
                xs = sorted(self.positions())
                self.assertGreaterEqual(min(b - a for a, b in zip(xs, xs[1:])), width - 1, (viewport, xs))
                self.page.clock.run_for(1000)

    def test_reader_keeps_its_place(self):
        kongi = self.creature("kongi")
        # Starting a reading for the friend being dragged drops it immediately.
        mochi = self.creature("mochi")
        mochi.click(force=True)
        x, y = self.grab("mochi")
        self.page.mouse.move(x + 20, y, steps=4)
        expect(mochi).to_have_class(re.compile("is-dragging"))
        self.page.evaluate("window.creatureStage.begin('Hello there')")
        expect(mochi).not_to_have_class(re.compile("is-dragging"))
        held = mochi.bounding_box()["x"]
        self.page.mouse.move(x + 90, y, steps=4)
        self.assertEqual(mochi.bounding_box()["x"], held)
        # Releasing over the friend after the forced drop is neither a tap nor a pet.
        box = mochi.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        self.page.mouse.up()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate(
            "JSON.parse(localStorage.getItem('campus-tts-affection')).mochi"), 1)
        self.page.evaluate("window.creatureStage.reset()")
        self.page.locator('.creature-choice[data-reader="kongi"]').click()
        self.generate()
        # A reaction from the ready state stops once the reading starts.
        for _ in range(3):
            kongi.click(force=True)
        expect(kongi.locator(".creature-pose")).to_have_class(re.compile("react-excited"))
        self.play()
        expect(kongi.locator(".creature-pose")).not_to_have_class(re.compile("react-"))
        # A reduced-motion round trip during the reading keeps listeners facing the reader.
        self.page.emulate_media(reduced_motion="reduce")
        self.page.wait_for_function("matchMedia('(prefers-reduced-motion: reduce)').matches")
        self.page.wait_for_timeout(100)
        self.page.emulate_media(reduced_motion="no-preference")
        self.page.wait_for_function("!matchMedia('(prefers-reduced-motion: reduce)').matches")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.look("mochi")[0], 2.4)
        before = kongi.bounding_box()["x"]
        x, y = self.grab("kongi")
        self.page.mouse.move(x - 60, y, steps=6)
        expect(kongi).not_to_have_class(re.compile("is-dragging"))
        self.page.mouse.up()
        self.assertEqual(kongi.bounding_box()["x"], before)
        expect(self.page.locator("#creature-bubble")).to_be_visible()

    def test_eyes_follow_pointer_and_friends_fall_asleep(self):
        stage = self.page.locator("#creature-stage")
        # A far pointer leaves the eyes alone; vertical glances only come from tracking.
        ex, ey = self.eye_center("mochi")
        self.page.mouse.move(ex, ey - 400)
        self.page.wait_for_timeout(150)
        self.assertEqual(self.look("mochi")[1], 0)
        ex, ey = self.eye_center("mochi")
        self.page.mouse.move(ex - 50, ey - 60)
        self.page.wait_for_timeout(150)
        look_x, look_y = self.look("mochi")
        self.assertLess(look_x, -0.5)
        self.assertLess(look_y, -0.5)
        ex, ey = self.eye_center("mochi")
        self.page.mouse.move(ex + 60, ey + 25)
        self.page.wait_for_timeout(150)
        look_x, look_y = self.look("mochi")
        self.assertGreater(look_x, 0.5)
        self.assertGreater(look_y, 0.3)
        # After the pointer leaves the window, coming back at 160px is not close enough to start.
        self.page.evaluate("document.documentElement.dispatchEvent(new PointerEvent('pointerleave'))")
        ex, ey = self.eye_center("mochi")
        self.page.mouse.move(ex, ey - 160)
        self.page.wait_for_timeout(150)
        self.assertEqual(self.look("mochi")[1], 0)
        # Switching to reduced motion mid-glance recentres every eye.
        self.page.emulate_media(reduced_motion="reduce")
        # The media change event arrives asynchronously after emulation.
        self.page.wait_for_function("""() => {
            const style = document.querySelector('[data-creature=mochi]').style;
            return style.getPropertyValue('--look-x') === '0.00px' && style.getPropertyValue('--look-y') === '0.00px';
        }""")
        self.page.emulate_media(reduced_motion="no-preference")
        stage.evaluate("s => { s.dataset.sleepAfter = '400'; }")
        expect(stage).to_have_attribute("data-sleeping", "true", timeout=4000)
        eyes = self.creature("popo").locator(".creature-eyes")
        self.assertIn("0.15", eyes.evaluate("e => getComputedStyle(e).transform"))
        positions = self.page.locator(".creature").evaluate_all(
            "els => els.map(e => e.getBoundingClientRect().x)")
        self.page.wait_for_timeout(600)
        self.assertEqual(positions, self.page.locator(".creature").evaluate_all(
            "els => els.map(e => e.getBoundingClientRect().x)"))
        self.page.mouse.move(600, 200)
        expect(stage).not_to_have_attribute("data-sleeping", "true")
        expect(self.page.locator(".creature-chat:visible")).to_have_count(3)
        # A prepared clip keeps everyone awake; a new reading wakes them up.
        self.generate()
        self.page.wait_for_timeout(1500)
        expect(stage).not_to_have_attribute("data-sleeping", "true")
        self.page.evaluate("window.creatureStage.reset()")
        expect(stage).to_have_attribute("data-sleeping", "true", timeout=4000)
        self.page.evaluate("window.creatureStage.begin('Wake up')")
        expect(stage).not_to_have_attribute("data-sleeping", "true")
        self.page.evaluate("window.creatureStage.reset()")

    def test_mobile_chat_reduced_motion_and_destroy(self):
        self.page.set_viewport_size({"width": 360, "height": 740})
        # Shrinking the window rescales the spread instead of piling friends at the edge.
        xs = sorted(self.positions())
        self.assertGreaterEqual(min(b - a for a, b in zip(xs, xs[1:])), 76, xs)
        for name in ("mochi", "kongi"):
            self.creature(name).click(force=True)
            chat = self.creature(name).locator(".creature-chat")
            expect(chat).to_be_visible()
            box = chat.bounding_box()
            self.assertGreaterEqual(box["x"], 0)
            self.assertLessEqual(box["x"] + box["width"], 360)
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.page.screenshot(path=str(self.artifacts / "mobile-petting.png"))
        pose = self.creature("popo").locator(".creature-pose")
        self.creature("popo").click(force=True)
        expect(pose).to_have_class(re.compile("react-hop"))
        self.page.emulate_media(reduced_motion="reduce")
        expect(pose).not_to_have_class(re.compile("react-"))
        self.creature("popo").click(force=True)
        expect(self.creature("popo").locator(".creature-chat")).to_be_visible()
        self.assertNotIn("react-", pose.get_attribute("class"))
        self.page.locator("#creature-stage").evaluate("s => { s.dataset.sleepAfter = '200'; }")
        self.page.evaluate("window.creatureStage.destroy()")
        self.page.wait_for_timeout(2200)
        expect(self.page.locator(".creature-emote")).to_have_count(0)
        expect(self.page.locator(".creature-chat:visible")).to_have_count(0)
        expect(self.page.locator("#creature-stage")).not_to_have_attribute("data-sleeping", "true")

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
