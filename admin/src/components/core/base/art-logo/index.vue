<!-- 系统logo -->
<template>
  <div class="flex-cc">
    <img :style="logoStyle" :src="logoSrc" alt="EverKB" class="w-full h-full" />
  </div>
</template>

<script setup lang="ts">
  import logoColor from '@imgs/common/logo.svg'
  import logoWhite from '@imgs/common/logo-white.svg'
  import { useSettingStore } from '@/store/modules/setting'

  defineOptions({ name: 'ArtLogo' })

  interface Props {
    /** logo 大小 */
    size?: number | string
    /** 版本：auto 跟随系统主题，color 固定彩色，white 固定白色 */
    variant?: 'auto' | 'color' | 'white'
  }

  const props = withDefaults(defineProps<Props>(), {
    size: 36,
    variant: 'auto'
  })

  const settingStore = useSettingStore()

  const logoSrc = computed(() => {
    if (props.variant !== 'auto') {
      return props.variant === 'white' ? logoWhite : logoColor
    }
    return settingStore.isDark ? logoWhite : logoColor
  })

  const logoStyle = computed(() => ({ width: `${props.size}px` }))
</script>
