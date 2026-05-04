# Theme Picker Web

独立的 `theme-picker` 前端子仓库骨架。

## 能力

- 主题选股主页面
- 历史结果恢复与重试
- 异步任务轮询
- 单票详情展示
- 独立运行的 Vite 开发环境

## 启动

```bash
npm install
npm run dev
```

默认会把 `/api` 代理到 `http://127.0.0.1:8765`。如需改后端地址，可配置：

```bash
VITE_API_URL=http://127.0.0.1:8765
```

如果是开发环境代理，也可以显式指定：

```bash
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8765
```

## 构建与测试

```bash
npm run lint
npm run test
npm run build
```

## 说明

- 该子仓库默认只包含 `theme-picker` 页面与其最小依赖。
- `发起深度分析` 在独立模式下会跳到一个占位 `/chat` 页面，方便后续接入独立问股前端。
