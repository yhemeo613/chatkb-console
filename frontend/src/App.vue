<template>
  <a-config-provider :locale="zhCN" :theme="theme">
    <router-view />
  </a-config-provider>
</template>

<script setup>
import zhCN from 'ant-design-vue/es/locale/zh_CN'

// 全局设计令牌：微信绿单强调色 + 小圆角 + 扁平工具风（详见 styles/variables.less）
const theme = {
  token: {
    colorPrimary: '#07c160',
    colorInfo: '#07c160',
    colorLink: '#06934e',
    borderRadius: 6,
    colorBgLayout: '#f6f7f9',
    colorBorder: '#d8dee5',
    colorBorderSecondary: '#e3e7ec',
    fontSize: 14,
  },
}
</script>
