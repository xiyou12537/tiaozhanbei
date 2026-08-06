<template>
  <div class="hero-molecule" aria-hidden="true">
    <div class="surface-grid">
      <span v-for="index in 90" :key="index" class="grid-dot"></span>
    </div>
    <div class="hud-ring ring-one"></div>
    <div class="hud-ring ring-two"></div>
    <svg viewBox="0 0 620 430" class="molecule-svg" role="img">
      <defs>
        <radialGradient id="goldAtom" cx="35%" cy="28%" r="70%">
          <stop offset="0%" stop-color="#fff7c6" />
          <stop offset="42%" stop-color="#f2c35b" />
          <stop offset="75%" stop-color="#b8791d" />
          <stop offset="100%" stop-color="#4a2c09" />
        </radialGradient>
        <radialGradient id="blueAtom" cx="38%" cy="30%" r="70%">
          <stop offset="0%" stop-color="#c8f6ff" />
          <stop offset="50%" stop-color="#34d6ff" />
          <stop offset="100%" stop-color="#0a55a8" />
        </radialGradient>
        <linearGradient id="goldBond" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#6b4b1a" />
          <stop offset="0.5" stop-color="#fff0aa" />
          <stop offset="1" stop-color="#a46c19" />
        </linearGradient>
      </defs>

      <g class="pulse-wave">
        <circle cx="286" cy="174" r="96" fill="none" stroke="#34d6ff" stroke-opacity="0.16" />
        <circle cx="286" cy="174" r="134" fill="none" stroke="#d9a63b" stroke-opacity="0.16" />
        <path d="M200 215 C232 182 250 228 279 191 C310 152 340 192 374 158" fill="none" stroke="#34d6ff" stroke-opacity=".34" stroke-width="2" />
      </g>

      <g class="molecule-chain">
        <path d="M187 204 L241 152 L315 168 L374 118 L445 139 L487 205 L446 269 L371 284 L316 236 L248 257 Z" fill="none" stroke="url(#goldBond)" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M248 257 L241 152 M315 168 L316 236 M445 139 L446 269" fill="none" stroke="url(#goldBond)" stroke-width="5" stroke-linecap="round" opacity=".82" />
        <circle cx="187" cy="204" r="21" fill="url(#goldAtom)" />
        <circle cx="241" cy="152" r="22" fill="url(#goldAtom)" />
        <circle cx="315" cy="168" r="20" fill="url(#goldAtom)" />
        <circle cx="374" cy="118" r="23" fill="url(#goldAtom)" />
        <circle cx="445" cy="139" r="21" fill="url(#goldAtom)" />
        <circle cx="487" cy="205" r="20" fill="url(#goldAtom)" />
        <circle cx="446" cy="269" r="22" fill="url(#goldAtom)" />
        <circle cx="371" cy="284" r="20" fill="url(#goldAtom)" />
        <circle cx="316" cy="236" r="22" fill="url(#goldAtom)" />
        <circle cx="248" cy="257" r="21" fill="url(#goldAtom)" />
        <circle cx="340" cy="314" r="13" fill="url(#blueAtom)" />
        <circle cx="525" cy="252" r="12" fill="url(#blueAtom)" />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.hero-molecule {
  position: absolute;
  inset: 88px 0 0 42%;
  overflow: hidden;
  opacity: 0.58;
  mix-blend-mode: screen;
  pointer-events: none;
}

.hero-molecule::before {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 88%;
  height: 52%;
  background:
    linear-gradient(135deg, transparent 0 48%, rgba(30, 140, 255, 0.18) 49%, transparent 50%),
    linear-gradient(45deg, transparent 0 48%, rgba(52, 214, 255, 0.14) 49%, transparent 50%);
  background-size: 42px 42px;
  transform: perspective(700px) rotateX(62deg) rotateZ(-10deg) translateY(36px);
  opacity: 0.75;
  content: "";
}

.surface-grid {
  position: absolute;
  right: -4%;
  bottom: 1%;
  width: 78%;
  height: 42%;
  display: grid;
  grid-template-columns: repeat(15, 1fr);
  gap: 18px 22px;
  transform: perspective(700px) rotateX(62deg) rotateZ(-10deg);
}

.grid-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #1e8cff;
  box-shadow: 0 0 14px rgba(30, 140, 255, 0.92);
}

.hud-ring {
  position: absolute;
  left: 14%;
  top: 16%;
  width: 280px;
  height: 280px;
  border: 1px solid rgba(217, 166, 59, 0.16);
  border-radius: 50%;
}

.ring-one {
  animation: slowSpin 18s linear infinite;
}

.ring-two {
  width: 360px;
  height: 360px;
  border-color: rgba(52, 214, 255, 0.1);
  transform: translate(-38px, -36px);
  animation: slowSpin 24s linear reverse infinite;
}

.molecule-svg {
  position: absolute;
  right: 2%;
  top: 8%;
  width: min(760px, 76vw);
  filter: drop-shadow(0 28px 45px rgba(0, 0, 0, 0.35));
}

.molecule-chain circle {
  filter: drop-shadow(0 0 14px rgba(242, 195, 91, 0.62));
}

.pulse-wave {
  animation: pulseFade 5s ease-in-out infinite;
}

@keyframes slowSpin {
  to {
    rotate: 360deg;
  }
}

@keyframes pulseFade {
  0%,
  100% {
    opacity: 0.58;
    transform: scale(1);
    transform-origin: 286px 174px;
  }

  50% {
    opacity: 1;
    transform: scale(1.04);
  }
}

@media (max-width: 960px) {
  .hero-molecule {
    inset: 360px -10% 0 4%;
    opacity: 0.55;
  }
}
</style>
