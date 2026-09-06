<template>
  <div class="stat-strip">
    <div class="cell" v-for="c in items" :key="c.label">
      <div class="label">{{ c.label }}</div>
      <div class="value" :class="c.tone">{{ c.value }}</div>
      <div class="sub" v-if="c.sub">{{ c.sub }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({ items: { type: Array, default: () => [] } })
</script>
