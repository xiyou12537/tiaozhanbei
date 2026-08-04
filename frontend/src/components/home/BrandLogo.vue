<template>
  <router-link class="brand-logo" to="/" :class="{ compact }" aria-label="量智硫光">
    <span class="brand-orbit" aria-hidden="true">
      <span class="orbit-ring ring-a"></span>
      <span class="orbit-ring ring-b"></span>
      <span class="orbit-core"></span>
      <span class="orbit-node node-a"></span>
      <span class="orbit-node node-b"></span>
      <span class="orbit-node node-c"></span>
      <span class="orbit-link link-a"></span>
      <span class="orbit-link link-b"></span>
      <span class="orbit-link link-c"></span>
    </span>
    <span class="brand-copy">
      <strong>量智硫光</strong>
      <small>锂硫量子材料平台</small>
    </span>
  </router-link>
</template>

<script setup>
defineProps({
  compact: {
    type: Boolean,
    default: false,
  },
})
</script>

<style scoped>
.brand-logo {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  color: #f4f8fb;
  text-decoration: none;
}

.brand-orbit {
  position: relative;
  width: 58px;
  height: 58px;
  flex: 0 0 58px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 48% 52%, rgba(52, 214, 255, 0.26), transparent 36%),
    radial-gradient(circle at 28% 22%, rgba(242, 195, 91, 0.24), transparent 26%),
    rgba(4, 10, 20, 0.82);
  box-shadow:
    0 0 0 1px rgba(120, 200, 255, 0.18),
    0 0 28px rgba(30, 140, 255, 0.32),
    inset 0 0 18px rgba(52, 214, 255, 0.18);
}

.compact .brand-orbit {
  width: 44px;
  height: 44px;
  flex-basis: 44px;
}

.orbit-ring,
.orbit-core,
.orbit-node,
.orbit-link {
  position: absolute;
  display: block;
}

.orbit-ring {
  inset: 8px;
  border: 1px solid rgba(52, 214, 255, 0.42);
  border-radius: 50%;
}

.ring-a {
  transform: rotate(-18deg) scaleX(0.72);
}

.ring-b {
  border-color: rgba(242, 195, 91, 0.46);
  transform: rotate(34deg) scaleX(0.66);
}

.orbit-core {
  left: 50%;
  top: 50%;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #34d6ff;
  box-shadow: 0 0 14px rgba(52, 214, 255, 0.9);
  transform: translate(-50%, -50%);
}

.orbit-node {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, #fff4b8, #d9a63b 58%, #7a4a10);
  box-shadow: 0 0 14px rgba(242, 195, 91, 0.78);
}

.node-a {
  left: 18px;
  top: 14px;
}

.node-b {
  right: 14px;
  top: 24px;
}

.node-c {
  left: 24px;
  bottom: 13px;
}

.compact .node-a {
  left: 13px;
  top: 11px;
}

.compact .node-b {
  right: 10px;
  top: 18px;
}

.compact .node-c {
  left: 18px;
  bottom: 10px;
}

.orbit-link {
  height: 1px;
  background: linear-gradient(90deg, rgba(242, 195, 91, 0.2), rgba(242, 195, 91, 0.82));
  transform-origin: left center;
}

.link-a {
  left: 23px;
  top: 19px;
  width: 22px;
  transform: rotate(23deg);
}

.link-b {
  left: 27px;
  top: 32px;
  width: 20px;
  transform: rotate(138deg);
}

.link-c {
  left: 22px;
  bottom: 18px;
  width: 18px;
  transform: rotate(-52deg);
}

.brand-copy {
  display: grid;
  gap: 4px;
}

.brand-copy strong {
  font-size: 1.58rem;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.02em;
}

.brand-copy small {
  color: #93a8bd;
  font-size: 0.78rem;
  letter-spacing: 0.24em;
}

.compact .brand-copy strong {
  font-size: 1.12rem;
}

.compact .brand-copy small {
  font-size: 0.68rem;
  letter-spacing: 0.18em;
}

@media (max-width: 720px) {
  .brand-copy small {
    display: none;
  }
}
</style>
