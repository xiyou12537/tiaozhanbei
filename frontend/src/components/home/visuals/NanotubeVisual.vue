<template>
  <img class="mini-visual" :src="imageSrc" alt="" aria-hidden="true" />
</template>

<script setup>
import imageSrc from '../../../assets/home/material-vg-cnt-glass.png'
</script>

<style scoped>
.mini-visual {
  position: relative;
  z-index: 2;
  width: 100%;
  min-height: 132px;
  border-radius: 8px;
  object-fit: cover;
  object-position: 66% 50%;
  filter: saturate(1.04) contrast(1.04) drop-shadow(0 0 16px rgba(52, 214, 255, 0.16));
}
</style>
