<template>
  <div class="projection" aria-hidden="true">
    <img :src="imageSrc" alt="" />
  </div>
</template>

<script setup>
import imageSrc from '../../../assets/home/material-li2s6-glass.png'
</script>

<style scoped>
.projection {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.projection::after {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 58% 72%, rgba(52, 214, 255, 0.22), transparent 30%),
    linear-gradient(90deg, rgba(4, 10, 20, 0) 54%, rgba(4, 10, 20, 0.22) 100%);
  pointer-events: none;
  content: "";
}

img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 58% 50%;
  filter: saturate(1.05) contrast(1.04);
  animation: moleculeFloat 5.4s ease-in-out infinite;
}

@keyframes moleculeFloat {
  0%,
  100% {
    transform: scale(1.02) translateY(0);
  }

  50% {
    transform: scale(1.04) translateY(-8px);
  }
}
</style>
