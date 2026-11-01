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
  const timers = new Set();
  const binSeconds = 0.04;
  const storageKey = "campus-tts-affection";
  const heartSteps = [5, 15, 30];
  const reactionMs = { hop: 450, excited: 750, land: 320, stretch: 900 };
  const labels = {
    generating: "…", ready: "준비 완료", speaking: "읽는 중",
    paused: "일시정지", waiting: "재생 대기"
  };
  const lines = {
    mochi: { pet: ["말랑말랑~", "간지러워!", "헤헤, 좋아!"], excited: "와아, 신난다!", wake: "하암~ 잘 잤다" },
    popo: { pet: ["폭신폭신!", "포포포~", "기분 최고!"], excited: "포포포포!!", wake: "벌써 아침이야?" },
    kongi: { pet: ["…좋아.", "콩!", "따뜻해."], excited: "콩콩콩!", wake: "음… 조금만 더…" }
  };
  const creatures = [...field.querySelectorAll(".creature")].map((button, index) => ({
    button, id: button.dataset.creature, name: button.dataset.name,
    label: button.getAttribute("aria-label"), lines: lines[button.dataset.creature],
    badge: button.querySelector(".creature-badge"),
    mouth: button.querySelector(".creature-mouth"),
    pose: button.querySelector(".creature-pose"),
    chat: button.querySelector(".creature-chat"),
    hearts: button.querySelector(".creature-hearts"),
    index, x: null, target: 0, minimum: 0, maximum: 0, width: 0, eyeFromBottom: 0,
    rest: index * 0.6 + 0.4, stay: 0, speed: [14, 25, 11][index], phase: index * 2,
    hover: false, tracking: false, dragging: false, chatting: false,
    chatTimer: null, reactTimer: null, pets: [], affection: 0
  }));
  let nextReader = "random";
  let clip = null;
  let state = "idle";
  let frame = null;
  let previousTime = null;
  let destroyed = false;
  let reducedMotion = motionPreference.matches;
  let fieldLeft = 0;
  let fieldBottom = 0;
  let gap = 88;
  let span = 0;
  let drag = null;
  let suppressClick = null;
  let pointer = null;
  let sleeping = false;
  let sleepTimer = null;
  let lastActivity = performance.now();

  function listen(target, type, handler) {
    target.addEventListener(type, handler);
    listeners.push(() => target.removeEventListener(type, handler));
  }

  function later(callback, delay) {
    const id = window.setTimeout(() => {
      timers.delete(id);
      callback();
    }, delay);
    timers.add(id);
    return id;
  }

  function cancelLater(id) {
    if (id === null) return;
    window.clearTimeout(id);
    timers.delete(id);
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function announce(message) {
    liveStatus.textContent = message;
  }

  function isActiveSpeaker(creature) {
    return Boolean(clip && creature === clip.speaker && state !== "idle");
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

  function heartLevel(count) {
    return heartSteps.filter(step => count >= step).length;
  }

  function readAffection() {
    let saved;
    try {
      saved = JSON.parse(window.localStorage.getItem(storageKey) || "{}") || {};
    } catch {
      // Blocked or corrupt storage is ignored; petting still works for this visit.
      return null;
    }
    return Object.fromEntries(creatures.map(creature => {
      const count = saved[creature.id];
      return [creature.id, Number.isSafeInteger(count) && count > 0 ? count : 0];
    }));
  }

  function loadAffection() {
    const saved = readAffection();
    if (!saved) return;
    for (const creature of creatures) {
      creature.affection = saved[creature.id];
      renderHearts(creature);
    }
  }

  function addAffection(creature) {
    // Merge counts another tab may have saved since this page loaded.
    const saved = readAffection();
    if (saved) {
      for (const other of creatures) other.affection = Math.max(other.affection, saved[other.id]);
    }
    creature.affection += 1;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(
        Object.fromEntries(creatures.map(creature => [creature.id, creature.affection]))));
    } catch {
      // Keep the in-memory count when storage is unavailable.
    }
    creatures.forEach(renderHearts);
  }

  function renderHearts(creature) {
    const level = heartLevel(creature.affection);
    creature.hearts.textContent = "♥".repeat(level);
    creature.button.setAttribute("aria-label",
      level ? `${creature.label} 친밀도 하트 ${level}개.` : creature.label);
  }

  function clearReaction(creature) {
    cancelLater(creature.reactTimer);
    creature.reactTimer = null;
    for (const kind of Object.keys(reactionMs)) creature.pose.classList.remove(`react-${kind}`);
  }

  function react(creature, kind) {
    clearReaction(creature);
    if (reducedMotion) return;
    // Reading the layout restarts the same animation on repeated taps.
    void creature.pose.offsetWidth;
    creature.pose.classList.add(`react-${kind}`);
    creature.reactTimer = later(() => clearReaction(creature), reactionMs[kind]);
  }

  function emote(creature, symbol, count) {
    for (let index = 0; index < count; index++) {
      if (creature.button.querySelectorAll(".creature-emote").length >= 6) return;
      const mark = document.createElement("span");
      mark.className = "creature-emote";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = symbol;
      mark.style.setProperty("--emote-x", `${((index - (count - 1) / 2) * 14 + Math.random() * 6 - 3).toFixed(1)}px`);
      mark.style.animationDelay = `${index * 90}ms`;
      creature.button.append(mark);
      later(() => mark.remove(), 1100 + index * 90);
    }
  }

  function hideChat(creature) {
    cancelLater(creature.chatTimer);
    creature.chatTimer = null;
    creature.chat.hidden = true;
    creature.chat.textContent = "";
    creature.chatting = false;
  }

  function showChat(creature, text) {
    // The reading bubble and the reader's badge own the space above the stage.
    if (!bubble.hidden || isActiveSpeaker(creature)) return;
    cancelLater(creature.chatTimer);
    creature.chat.textContent = text;
    creature.chat.hidden = false;
    creature.chatting = true;
    placeChat(creature);
    creature.chatTimer = later(() => hideChat(creature), 1800);
  }

  function placeChat(creature) {
    // Keep a friend's line on screen even when it stands at the edge of the field.
    creature.chat.style.setProperty("--chat-shift", "0px");
    const rect = creature.chat.getBoundingClientRect();
    const limit = root.clientWidth - 8;
    const shift = rect.left < 8 ? 8 - rect.left : Math.min(0, limit - rect.right);
    creature.chat.style.setProperty("--chat-shift", `${shift.toFixed(1)}px`);
  }

  function pet(creature) {
    const now = performance.now();
    creature.pets = creature.pets.filter(time => now - time < 1500);
    creature.pets.push(now);
    const excited = creature.pets.length >= 3;
    if (excited) creature.pets = [];
    const before = heartLevel(creature.affection);
    addAffection(creature);
    // A reader keeps still so the mouth stays in sync with the audio.
    if (!(isActiveSpeaker(creature) && !bubble.hidden)) react(creature, excited ? "excited" : "hop");
    emote(creature, "♥", excited ? 3 : 1);
    const pool = creature.lines.pet;
    showChat(creature, excited ? creature.lines.excited : pool[Math.floor(Math.random() * pool.length)]);
    const level = heartLevel(creature.affection);
    return level > before ? ` ${creature.name}와 더 친해졌어요. 하트 ${level}개!` : "";
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

  function setLook(creature, x, y = 0) {
    creature.button.style.setProperty("--look-x", `${x.toFixed(2)}px`);
    creature.button.style.setProperty("--look-y", `${y.toFixed(2)}px`);
  }

  function lookAtSpeaker() {
    for (const creature of creatures) {
      creature.tracking = false;
      setLook(creature, creature === clip.speaker ? 0 : Math.sign(clip.speaker.x - creature.x) * 2.4);
    }
  }

  function lookAtPointer(creature) {
    // Eyes follow a nearby pointer in any direction; 140px starts and 180px ends the glance.
    if (!pointer) return false;
    const dx = pointer.x - (fieldLeft + creature.x + creature.width / 2);
    const dy = pointer.y - (fieldBottom - creature.eyeFromBottom);
    const distance = Math.hypot(dx, dy);
    creature.tracking = distance < (creature.tracking ? 180 : 140);
    if (!creature.tracking) return false;
    const angle = Math.atan2(dy, dx);
    const reach = clamp(distance / 40, 0, 1);
    setLook(creature, Math.cos(angle) * 2.4 * reach, Math.sin(angle) * 2 * reach);
    return true;
  }

  function clearLooks() {
    for (const creature of creatures) {
      creature.tracking = false;
      setLook(creature, 0);
    }
  }

  function renderState(nextState) {
    state = nextState;
    lastActivity = performance.now();
    if (sleeping && state !== "idle") wake();
    // The release that follows a drag cut short here is still not a tap.
    if (drag && isActiveSpeaker(drag.creature)) suppressClick = endDrag();
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
      if (showBubble || active) hideChat(creature);
      if (showBubble && active) clearReaction(creature);
      setMouth(creature, 0);
      creature.button.style.setProperty("--bob", "0px");
    }
    if (clip && showBubble) lookAtSpeaker();
    syncSpace();
    if (firstExpansion) revealAudioIfCovered();
    startAnimation();
  }

  function resize() {
    const width = field.clientWidth;
    const fieldRect = field.getBoundingClientRect();
    fieldLeft = fieldRect.left;
    fieldBottom = fieldRect.bottom;
    for (const creature of creatures) {
      const buttonRect = creature.button.getBoundingClientRect();
      const figureRect = creature.button.querySelector(".creature-figure").getBoundingClientRect();
      creature.width = creature.button.offsetWidth;
      creature.eyeFromBottom = buttonRect.bottom - (figureRect.top + figureRect.height * 34 / 60);
      // Every friend may roam the whole field.
      creature.minimum = 4;
      creature.maximum = Math.max(creature.minimum, width - creature.width - 4);
    }
    const { minimum, maximum, width: friendWidth } = creatures[0];
    const previousSpan = span;
    span = maximum - minimum;
    // Keep friends a body apart, or as far apart as a narrow field allows.
    gap = Math.min(friendWidth + 12, span / Math.max(1, creatures.length - 1));
    creatures.forEach((creature, index) => {
      if (creature.x === null) {
        // Start spread out: left edge, middle and right edge.
        creature.x = minimum + span * index / Math.max(1, creatures.length - 1);
        creature.target = creature.x;
      } else if (previousSpan > 0 && span !== previousSpan) {
        // Scale instead of clamping so a narrower screen keeps the friends apart and in order.
        const scale = span / previousSpan;
        creature.x = minimum + (creature.x - minimum) * scale;
        creature.target = minimum + (creature.target - minimum) * scale;
      }
      creature.x = clamp(creature.x, creature.minimum, creature.maximum);
      creature.target = clamp(creature.target, creature.minimum, creature.maximum);
      creature.button.style.setProperty("--creature-x", `${creature.x.toFixed(2)}px`);
      if (creature.chatting) placeChat(creature);
    });
    // A resize mid-drag keeps the friend under the pointer from here on.
    if (drag) {
      drag.originX = drag.creature.x;
      drag.startX = drag.lastX;
    }
    positionBubble();
    syncSpace();
  }

  function nearestDistance(creature, x = creature.x) {
    let nearest = Infinity;
    for (const other of creatures) {
      if (other !== creature) nearest = Math.min(nearest, Math.abs(other.x - x));
    }
    return nearest;
  }

  function anchored(creature) {
    return isActiveSpeaker(creature) || creature.hover || creature.dragging;
  }

  function blocked(creature, next) {
    // A step may not move closer to a friend that is already within the gap,
    // except one that cannot move itself; walking past it is the only way out.
    return creatures.some(other => {
      if (other === creature || anchored(other)) return false;
      const after = Math.abs(other.x - next);
      return after < gap && after < Math.abs(other.x - creature.x);
    });
  }

  function chooseTarget(creature) {
    const before = (a, b) => a.x < b.x || (a.x === b.x && a.index < b.index);
    const others = creatures.filter(other => other !== creature);
    const left = others.filter(other => before(other, creature));
    const right = others.filter(other => before(creature, other));
    let lo = Math.max(creature.minimum, ...left.map(other => other.x + gap));
    let hi = Math.min(creature.maximum, ...right.map(other => other.x - gap));
    if (lo > hi) {
      // Crowded: an outer friend steps outward and a friend boxed in on both sides waits.
      if (left.length && right.length) return creature.x;
      const direction = left.length ? 1 : -1;
      const outward = clamp(creature.x + direction * gap, creature.minimum, creature.maximum);
      if (Math.abs(outward - creature.x) >= 1) return outward;
      // Pinned against the edge: head for the roomiest spot anywhere instead.
      lo = creature.minimum;
      hi = creature.maximum;
    }
    // Pick the roomiest of a few random spots between the neighbours.
    let best = creature.x;
    let bestScore = -Infinity;
    for (let attempt = 0; attempt < 5; attempt++) {
      const candidate = lo + Math.random() * (hi - lo);
      const score = Math.min(...others.map(other =>
        Math.min(Math.abs(candidate - other.x), Math.abs(candidate - other.target))));
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    }
    return best;
  }

  function moveCreature(creature, x) {
    creature.x = clamp(x, creature.minimum, creature.maximum);
    creature.target = creature.x;
    // Stay where the visitor put it for a while; the others make room meanwhile.
    creature.stay = 3 + Math.random() * 3;
    creature.rest = creature.stay;
    creature.button.style.setProperty("--creature-x", `${creature.x.toFixed(2)}px`);
    if (clip && !bubble.hidden) lookAtSpeaker();
  }

  function startDrag(creature, event) {
    // One friend at a time: a second finger must not orphan the first drag.
    if (drag || event.button !== 0 || isActiveSpeaker(creature)) return;
    drag = {
      creature, pointerId: event.pointerId, active: false, swingTimer: null,
      startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastTime: event.timeStamp,
      originX: creature.x
    };
  }

  function swing(step, now) {
    // Shaking a friend fast makes it dizzy until the pointer slows down for 250ms.
    const speed = Math.abs(step) / Math.max(1, now - drag.lastTime);
    drag.lastTime = now;
    if (speed <= 0.8) return;
    const { creature } = drag;
    creature.button.classList.add("is-swinging");
    cancelLater(drag.swingTimer);
    drag.swingTimer = later(() => creature.button.classList.remove("is-swinging"), 250);
  }

  function moveDrag(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const offset = event.clientX - drag.startX;
    if (!drag.active) {
      const rise = event.clientY - drag.startY;
      if (Math.abs(offset) < 6 && Math.abs(rise) < 6) return;
      // A mostly vertical gesture is a page scroll, not a lift.
      if (Math.abs(rise) > Math.abs(offset)) {
        drag = null;
        return;
      }
      const { creature } = drag;
      drag.active = true;
      creature.dragging = true;
      creature.button.classList.add("is-dragging");
      clearReaction(creature);
      hideChat(creature);
      try {
        creature.button.setPointerCapture(drag.pointerId);
      } catch {
        // The pointer may already be gone; the window listeners still end the drag.
      }
    }
    const step = event.clientX - drag.lastX;
    drag.lastX = event.clientX;
    swing(step, event.timeStamp);
    if (step) drag.creature.button.style.setProperty("--tilt", `${Math.sign(step) * 7}deg`);
    moveCreature(drag.creature, drag.originX + offset);
  }

  function endDrag(event) {
    if (!drag || (event && event.pointerId !== drag.pointerId)) return null;
    const { creature, pointerId, active, swingTimer } = drag;
    drag = null;
    cancelLater(swingTimer);
    if (!active) return null;
    creature.dragging = false;
    creature.button.classList.remove("is-dragging", "is-swinging");
    creature.button.style.setProperty("--tilt", "0deg");
    if (creature.button.hasPointerCapture(pointerId)) creature.button.releasePointerCapture(pointerId);
    return creature;
  }

  function fallAsleep() {
    sleeping = true;
    stage.dataset.sleeping = "true";
    for (const creature of creatures) {
      clearReaction(creature);
      hideChat(creature);
      creature.button.style.setProperty("--bob", "0px");
    }
    clearLooks();
  }

  function wake() {
    sleeping = false;
    delete stage.dataset.sleeping;
    creatures.forEach((creature, index) => later(() => {
      // A tap that woke everyone already gave this friend its own reaction.
      if (sleeping || creature.reactTimer || creature.chatting || creature.dragging) return;
      if (isActiveSpeaker(creature) && !bubble.hidden) return;
      react(creature, "stretch");
      showChat(creature, creature.lines.wake);
    }, index * 160));
  }

  function noteActivity() {
    lastActivity = performance.now();
    if (sleeping) wake();
  }

  function checkSleep() {
    sleepTimer = null;
    if (destroyed) return;
    const delay = Number(stage.dataset.sleepAfter) || 60000;
    const idleFor = performance.now() - lastActivity;
    if (!sleeping && state === "idle" && !drag && idleFor >= delay) fallAsleep();
    // Poll at most once a second so a shortened delay takes effect without a reload.
    sleepTimer = window.setTimeout(checkSleep, sleeping ? 1000 : clamp(delay - idleFor, 100, 1000));
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
      const held = creature.hover || creature.dragging || creature.chatting || sleeping;
      let bob = 0;
      if (speaker && state === "speaking") {
        const amplitude = speakingAmplitude();
        setMouth(creature, amplitude);
        if (!held) bob = -amplitude * 2.5;
      } else {
        setMouth(creature, 0);
      }
      let look = null;
      if (!held && !gathering && !(speaker && ["generating", "ready"].includes(state))) {
        creature.phase += elapsed * (creature.id === "popo" ? 9 : 5);
        const distance = creature.target - creature.x;
        const next = creature.x + Math.sign(distance) * Math.min(Math.abs(distance), creature.speed * elapsed);
        if (Math.abs(distance) > 0.5 && blocked(creature, next)) {
          // Someone stepped into the path: stop here and pick again shortly.
          creature.target = creature.x;
          creature.rest = 0.4 + Math.random() * 0.6;
        }
        if (Math.abs(creature.target - creature.x) > 0.5) {
          creature.x = next;
          look = Math.sign(distance) * 1.8;
          bob = creature.id === "popo" ? -Math.max(0, Math.sin(creature.phase)) * 5 : -Math.abs(Math.sin(creature.phase)) * 1.4;
        } else {
          creature.stay = Math.max(0, creature.stay - elapsed);
          creature.rest -= elapsed;
          // A crowded friend moves on soon, unless the visitor just put it there.
          if (!creature.stay && nearestDistance(creature) < gap) creature.rest = Math.min(creature.rest, 0.3);
          if (creature.rest <= 0) {
            creature.target = chooseTarget(creature);
            creature.rest = creature.id === "kongi" ? 3 + Math.random() * 5 : 1 + Math.random() * 2.5;
          }
          look = Math.sin(creature.phase * 0.3);
        }
        creature.button.style.setProperty("--creature-x", `${creature.x.toFixed(2)}px`);
      }
      if (gathering || sleeping) {
        creature.tracking = false;
      } else if (!lookAtPointer(creature)) {
        setLook(creature, look ?? 0);
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

  function chooseReader(id, extra = "") {
    const creature = creatures.find(candidate => candidate.id === id);
    if (!creature) return;
    nextReader = creature.id;
    renderSelection();
    announce(`새로 만드는 음성은 ${creature.name}의 목소리로 읽어요.${extra}`);
  }

  for (const button of choiceButtons) {
    listen(button, "click", () => chooseReader(button.dataset.reader));
  }
  for (const creature of creatures) {
    listen(creature.button, "click", () => {
      // Dropping a dragged friend must not also count as a tap.
      if (suppressClick === creature) {
        suppressClick = null;
        return;
      }
      chooseReader(creature.id, pet(creature));
    });
    // Friends are pointer-only: a click must not leave focus behind for Enter or Space.
    listen(creature.button, "mousedown", event => event.preventDefault());
    listen(creature.button, "pointerdown", event => startDrag(creature, event));
    listen(creature.button, "lostpointercapture", event => {
      const dropped = endDrag(event);
      if (dropped) react(dropped, "land");
    });
    listen(creature.button, "pointerenter", event => { creature.hover = event.pointerType !== "touch"; });
    listen(creature.button, "pointerleave", () => { creature.hover = false; });
  }
  listen(randomButton, "click", () => {
    nextReader = "random";
    renderSelection();
    announce("다음 문장을 읽을 친구를 랜덤으로 골라요.");
  });
  listen(window, "pointermove", event => {
    noteActivity();
    if (event.pointerType !== "touch") pointer = { x: event.clientX, y: event.clientY };
    moveDrag(event);
  });
  listen(root, "pointerleave", () => {
    pointer = null;
    // A pointer coming back must cross the 140px start line again.
    for (const creature of creatures) creature.tracking = false;
  });
  listen(window, "pointerup", event => {
    const dropped = endDrag(event);
    if (dropped) {
      suppressClick = dropped;
      react(dropped, "land");
    }
    if (!suppressClick) return;
    // Only the click generated by this same release is skipped.
    const skipped = suppressClick;
    later(() => { if (suppressClick === skipped) suppressClick = null; }, 0);
  });
  listen(window, "pointercancel", event => {
    // No click follows a cancelled pointer.
    suppressClick = null;
    const dropped = endDrag(event);
    if (dropped) react(dropped, "land");
  });
  listen(window, "storage", event => {
    if (event.key === storageKey || event.key === null) loadAffection();
  });
  for (const type of ["pointerdown", "keydown", "wheel", "touchstart", "scroll"]) {
    listen(window, type, noteActivity);
  }
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
    if (document.hidden) {
      endDrag();
      stopAnimation();
    } else {
      if (state === "speaking" && audio.ended) ended();
      else if (state === "speaking" && audio.paused) renderState("paused");
      startAnimation();
    }
  });
  listen(motionPreference, "change", () => {
    reducedMotion = motionPreference.matches;
    for (const creature of creatures) clearReaction(creature);
    clearLooks();
    // The loop never re-aims eyes while gathered, so restore the glance at the reader here.
    if (clip && !bubble.hidden) lookAtSpeaker();
    stopAnimation();
    startAnimation();
  });
  const observer = new ResizeObserver(resize);
  observer.observe(stage);
  loadAffection();
  renderSelection();
  resize();
  renderState("idle");
  checkSleep();

  window.creatureStage = Object.freeze({
    begin, ready, reset, fail: reset,
    destroy() {
      if (destroyed) return;
      reset();
      destroyed = true;
      endDrag();
      stopAnimation();
      window.clearTimeout(sleepTimer);
      for (const id of timers) window.clearTimeout(id);
      timers.clear();
      for (const creature of creatures) {
        clearReaction(creature);
        hideChat(creature);
        for (const mark of creature.button.querySelectorAll(".creature-emote")) mark.remove();
      }
      delete stage.dataset.sleeping;
      observer.disconnect();
      for (const removeListener of listeners) removeListener();
      root.style.removeProperty("--creature-stage-height");
      root.style.removeProperty("--creature-bubble-space");
      root.style.removeProperty("scroll-padding-bottom");
    }
  });
})();
