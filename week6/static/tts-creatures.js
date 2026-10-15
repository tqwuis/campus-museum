(() => {
  "use strict";

  const stage = document.querySelector("#creature-stage");
  const audio = document.querySelector("#audio");
  if (!stage || !audio) return;

  const field = document.querySelector("#creature-field");
  const bubble = document.querySelector("#creature-bubble");
  const bubbleName = document.querySelector("#creature-bubble-name");
  const bubbleState = document.querySelector("#creature-bubble-state");
  const quote = document.querySelector("#creature-quote");
  const selection = document.querySelector("#creature-selection");
  const randomButton = document.querySelector("#creature-random");
  const choiceButtons = [...document.querySelectorAll(".creature-choice[data-reader]")];
  const liveStatus = document.querySelector("#creature-status");
  const root = document.documentElement;
  const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  const listeners = [];
  const binSeconds = 0.04;
  const labels = {
    generating: "…", ready: "준비 완료", speaking: "읽는 중",
    paused: "일시정지", waiting: "재생 대기"
  };
  const creatures = [...field.querySelectorAll(".creature")].map((button, index) => ({
    button, id: button.dataset.creature, name: button.dataset.name,
    badge: button.querySelector(".creature-badge"),
    mouth: button.querySelector(".creature-mouth"),
    x: null, target: 0, minimum: 0, maximum: 0, rest: index * 0.6 + 0.4,
    speed: [14, 25, 11][index], phase: index * 2, hover: false, focused: false
  }));
  let nextReader = "random";
  let clip = null;
  let state = "idle";
  let frame = null;
  let previousTime = null;
  let destroyed = false;
  let reducedMotion = motionPreference.matches;

  function listen(target, type, handler) {
    target.addEventListener(type, handler);
    listeners.push(() => target.removeEventListener(type, handler));
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function announce(message) {
    liveStatus.textContent = message;
  }

  function renderSelection() {
    const selected = creatures.find(creature => creature.id === nextReader);
    selection.textContent = `다음 문장 읽을 친구: ${selected ? selected.name : "랜덤"}`;
    randomButton.setAttribute("aria-pressed", String(!selected));
    for (const button of choiceButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.reader === nextReader));
    }
    for (const creature of creatures) {
      const chosen = creature === selected;
      creature.button.classList.toggle("is-selected", chosen);
      creature.button.setAttribute("aria-pressed", String(chosen));
    }
  }

  function setMouth(creature, amplitude) {
    creature.mouth.setAttribute("ry", (1.3 + amplitude * 7.7).toFixed(2));
  }

  function stopGestures() {
    for (const creature of creatures) {
      setMouth(creature, 0);
      creature.button.style.setProperty("--bob", "0px");
    }
  }

  function syncSpace() {
    const stageHeight = Math.ceil(stage.getBoundingClientRect().height);
    const bubbleSpace = bubble.hidden ? 0 : Math.ceil(bubble.getBoundingClientRect().height) + 12;
    root.style.setProperty("--creature-stage-height", `${stageHeight}px`);
    root.style.setProperty("--creature-bubble-space", `${bubbleSpace}px`);
    root.style.scrollPaddingBottom = `${stageHeight + bubbleSpace + 12}px`;
  }

  function positionBubble() {
    if (bubble.hidden || !clip) return;
    const stageRect = stage.getBoundingClientRect();
    const speakerRect = clip.speaker.button.getBoundingClientRect();
    const width = bubble.getBoundingClientRect().width;
    const speakerX = speakerRect.left + speakerRect.width / 2 - stageRect.left;
    const center = clamp(speakerX, width / 2 + 12, stageRect.width - width / 2 - 12);
    bubble.style.left = `${center}px`;
    bubble.style.setProperty("--tail-x", `${clamp(speakerX - center + width / 2, 18, width - 18)}px`);
  }

  function revealAudioIfCovered() {
    if (audio.hidden || bubble.hidden) return;
    const audioRect = audio.getBoundingClientRect();
    const bubbleRect = bubble.getBoundingClientRect();
    const obstruction = Math.min(stage.getBoundingClientRect().top, bubbleRect.top);
    // Only adjust a control already in view; playback must not pull a reader down the page.
    if (audioRect.height && audioRect.bottom > 0 && audioRect.top < window.innerHeight &&
        audioRect.bottom > obstruction - 12 && audioRect.top < stage.getBoundingClientRect().top) {
      window.scrollBy({ top: audioRect.bottom - obstruction + 12, behavior: "instant" });
    }
  }

  function renderState(nextState) {
    state = nextState;
    stage.dataset.state = state;
    if (clip) stage.dataset.speaker = clip.speaker.id;
    else delete stage.dataset.speaker;
    const showBubble = Boolean(clip && ["speaking", "paused", "waiting"].includes(state));
    const firstExpansion = showBubble && bubble.hidden;
    bubble.hidden = !showBubble;
    if (showBubble) {
      bubbleName.textContent = clip.speaker.name;
      bubbleState.textContent = labels[state];
      if (quote.textContent !== clip.text) quote.textContent = clip.text;
      positionBubble();
    }
    for (const creature of creatures) {
      const active = clip && creature === clip.speaker && state !== "idle";
      creature.button.dataset.state = active ? state : "idle";
      creature.button.classList.toggle("is-speaker", Boolean(active));
      creature.badge.hidden = !active;
      creature.badge.textContent = active ? labels[state] : "";
      setMouth(creature, 0);
      creature.button.style.setProperty("--bob", "0px");
    }
    if (clip && showBubble) {
      for (const creature of creatures) {
        const look = creature === clip.speaker ? 0 : Math.sign(clip.speaker.x - creature.x) * 2.4;
        creature.button.style.setProperty("--look-x", `${look}px`);
      }
    }
    syncSpace();
    if (firstExpansion) revealAudioIfCovered();
    startAnimation();
  }

  function resize() {
    const width = field.clientWidth;
    const laneWidth = width / creatures.length;
    creatures.forEach((creature, index) => {
      const buttonWidth = creature.button.offsetWidth;
      creature.minimum = laneWidth * index + 4;
      creature.maximum = Math.max(creature.minimum, laneWidth * (index + 1) - buttonWidth - 4);
      if (creature.x === null) creature.x = (creature.minimum + creature.maximum) / 2;
      creature.x = clamp(creature.x, creature.minimum, creature.maximum);
      creature.target = clamp(creature.target, creature.minimum, creature.maximum);
      creature.button.style.setProperty("--creature-x", `${creature.x.toFixed(2)}px`);
    });
    positionBubble();
    syncSpace();
  }

  function buildEnvelope(buffer) {
    const samplesPerBin = Math.max(1, Math.round(buffer.sampleRate * binSeconds));
    const levels = new Float32Array(Math.ceil(buffer.length / samplesPerBin));
    let peak = 0;
    for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
      const samples = buffer.getChannelData(channel);
      for (let bin = 0; bin < levels.length; bin++) {
        const start = bin * samplesPerBin;
        const end = Math.min(samples.length, start + samplesPerBin);
        let sum = 0;
        for (let index = start; index < end; index++) sum += samples[index] * samples[index];
        levels[bin] += sum / ((end - start) * buffer.numberOfChannels);
      }
    }
    for (let bin = 0; bin < levels.length; bin++) {
      levels[bin] = Math.sqrt(levels[bin]);
      peak = Math.max(peak, levels[bin]);
    }
    return { levels, peak, seconds: samplesPerBin / buffer.sampleRate };
  }

  function speakingAmplitude() {
    if (!clip || !clip.envelope || audio.paused || audio.ended || audio.seeking) return 0;
    const { levels, peak, seconds } = clip.envelope;
    const level = levels[Math.floor(audio.currentTime / seconds)] || 0;
    const silence = Math.max(0.003, peak * 0.045);
    return level <= silence || peak <= silence ? 0 : Math.sqrt(clamp((level - silence) / (peak - silence), 0, 1));
  }

  function animate(time) {
    frame = null;
    if (destroyed || document.hidden || reducedMotion) return;
    const elapsed = previousTime === null ? 0 : Math.min(0.05, (time - previousTime) / 1000);
    previousTime = time;
    const gathering = ["speaking", "paused", "waiting"].includes(state);
    for (const creature of creatures) {
      const speaker = clip && creature === clip.speaker;
      const held = creature.hover || creature.focused;
      let bob = 0;
      if (speaker && state === "speaking") {
        const amplitude = speakingAmplitude();
        setMouth(creature, amplitude);
        if (!held) bob = -amplitude * 2.5;
      } else {
        setMouth(creature, 0);
      }
      if (!held && !gathering && !(speaker && ["generating", "ready"].includes(state))) {
        creature.phase += elapsed * (creature.id === "popo" ? 9 : 5);
        const distance = creature.target - creature.x;
        if (Math.abs(distance) > 0.5) {
          creature.x += Math.sign(distance) * Math.min(Math.abs(distance), creature.speed * elapsed);
          creature.button.style.setProperty("--look-x", `${Math.sign(distance) * 1.8}px`);
          bob = creature.id === "popo" ? -Math.max(0, Math.sin(creature.phase)) * 5 : -Math.abs(Math.sin(creature.phase)) * 1.4;
        } else {
          creature.rest -= elapsed;
          if (creature.rest <= 0) {
            creature.target = creature.minimum + Math.random() * (creature.maximum - creature.minimum);
            creature.rest = creature.id === "kongi" ? 3 + Math.random() * 5 : 1 + Math.random() * 2.5;
          }
          creature.button.style.setProperty("--look-x", `${Math.sin(creature.phase * 0.3).toFixed(2)}px`);
        }
        creature.button.style.setProperty("--creature-x", `${creature.x.toFixed(2)}px`);
      }
      creature.button.style.setProperty("--bob", `${bob.toFixed(2)}px`);
    }
    frame = window.requestAnimationFrame(animate);
  }

  function stopAnimation() {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
    previousTime = null;
    stopGestures();
  }

  function startAnimation() {
    if (!destroyed && !document.hidden && !reducedMotion && frame === null) {
      previousTime = null;
      frame = window.requestAnimationFrame(animate);
    }
  }

  function begin(text) {
    if (destroyed) return null;
    const speaker = nextReader === "random"
      ? creatures[Math.floor(Math.random() * creatures.length)]
      : creatures.find(creature => creature.id === nextReader);
    clip = { speaker, text: String(text).trim(), envelope: null };
    quote.textContent = "";
    quote.scrollTop = 0;
    renderState("generating");
    announce(`${speaker.name}가 음성을 준비하고 있어요.`);
    return speaker.id;
  }

  function ready(buffer) {
    if (destroyed || !clip || state !== "generating") return;
    clip.envelope = buildEnvelope(buffer);
    renderState("ready");
    announce(`${clip.speaker.name}: 재생하면 읽어줄게!`);
  }

  function reset() {
    if (destroyed) return;
    clip = null;
    quote.textContent = "";
    renderState("idle");
    announce("");
  }

  function playing() {
    if (!clip || !clip.envelope || state === "generating") return;
    renderState("speaking");
    announce(`${clip.speaker.name}가 읽는 중이에요.`);
  }

  function ended() {
    if (!clip || !clip.envelope || state === "generating") return;
    renderState("idle");
    announce(`${clip.speaker.name}가 다 읽었어요. 다시 재생할 수 있어요.`);
  }

  function chooseReader(id) {
    const creature = creatures.find(candidate => candidate.id === id);
    if (!creature) return;
    nextReader = creature.id;
    renderSelection();
    announce(`새로 만드는 음성은 ${creature.name}의 목소리로 읽어요.`);
  }

  for (const button of choiceButtons) {
    listen(button, "click", () => chooseReader(button.dataset.reader));
  }
  for (const creature of creatures) {
    listen(creature.button, "click", () => chooseReader(creature.id));
    listen(creature.button, "pointerenter", event => { creature.hover = event.pointerType !== "touch"; });
    listen(creature.button, "pointerleave", () => { creature.hover = false; });
    listen(creature.button, "focus", () => { creature.focused = true; });
    listen(creature.button, "blur", () => { creature.focused = false; });
  }
  listen(randomButton, "click", () => {
    nextReader = "random";
    renderSelection();
    announce("다음 문장을 읽을 친구를 랜덤으로 골라요.");
  });
  listen(audio, "playing", playing);
  listen(audio, "pause", () => {
    if (!clip || !clip.envelope || bubble.hidden || audio.ended) return;
    renderState("paused");
    announce(`${clip.speaker.name}가 잠깐 쉬고 있어요.`);
  });
  listen(audio, "waiting", () => {
    if (clip && clip.envelope && !bubble.hidden) renderState("waiting");
  });
  listen(audio, "seeking", () => {
    if (clip && clip.envelope && !bubble.hidden) renderState(audio.paused ? "paused" : "waiting");
  });
  listen(audio, "seeked", () => {
    if (!clip || !clip.envelope || bubble.hidden) return;
    if (audio.paused) renderState("paused");
    else if (audio.readyState >= 3) playing();
  });
  listen(audio, "ended", ended);
  listen(audio, "error", () => {
    if (audio.error && clip && clip.envelope && state !== "generating") reset();
  });
  listen(window, "resize", resize);
  listen(document, "visibilitychange", () => {
    if (document.hidden) stopAnimation();
    else {
      if (state === "speaking" && audio.ended) ended();
      else if (state === "speaking" && audio.paused) renderState("paused");
      startAnimation();
    }
  });
  listen(motionPreference, "change", () => {
    reducedMotion = motionPreference.matches;
    stopAnimation();
    startAnimation();
  });
  const observer = new ResizeObserver(resize);
  observer.observe(stage);
  renderSelection();
  resize();
  renderState("idle");

  window.creatureStage = Object.freeze({
    begin, ready, reset, fail: reset,
    destroy() {
      if (destroyed) return;
      reset();
      destroyed = true;
      stopAnimation();
      observer.disconnect();
      for (const removeListener of listeners) removeListener();
      root.style.removeProperty("--creature-stage-height");
      root.style.removeProperty("--creature-bubble-space");
      root.style.removeProperty("scroll-padding-bottom");
    }
  });
})();
