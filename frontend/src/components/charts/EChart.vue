<template>
  <div ref="el" :style="{ height, width: '100%' }" />
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '300px' },
})

const el = ref(null)
let chart = null
let ro = null

onMounted(() => {
  chart = echarts.init(el.value)
  chart.setOption(props.option)
  ro = new ResizeObserver(() => chart && chart.resize())
  ro.observe(el.value)
})

watch(() => props.option, (o) => chart && chart.setOption(o, true), { deep: true })

onUnmounted(() => {
  ro?.disconnect()
  chart?.dispose()
  chart = null
})
</script>
