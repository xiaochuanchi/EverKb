import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";

import "element-plus/dist/index.css";

import App from "./App.vue";
import router from "./router";

// 启动顺序：pinia 必须先于 router（守卫内读 auth store）
createApp(App).use(createPinia()).use(router).use(ElementPlus).mount("#app");
