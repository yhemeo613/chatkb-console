<template>
  <a-result status="403" title="403" sub-title="抱歉，你没有访问该页面的权限">
    <template #extra>
      <a-button type="primary" @click="$router.push('/dashboard')">回工作台</a-button>
    </template>
  </a-result>
</template>
