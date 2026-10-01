<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const pickA = ref<number | null>(null)
const pickB = ref<number | null>(null)
const busy = ref(false)
const okMsg = ref('')
const errMsg = ref('')

const activeRows = computed(() => rows.value.filter(r => r.status === 'active'))
const canMerge = computed(() =>
  pickA.value != null && pickB.value != null && pickA.value !== pickB.value && !busy.value
)

async function refresh() { rows.value = await api('/vendors') }

function errText(e: any): string {
  try {
    const body = JSON.parse(e?.message || '')
    if (body?.detail) return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
  } catch { /* 非 JSON 错误体 */ }
  return e?.message || '操作失败'
}

async function merge() {
  if (!canMerge.value) return
  busy.value = true
  okMsg.value = ''
  errMsg.value = ''
  try {
    const r = await api('/vendors/merge', {
      method: 'POST',
      body: JSON.stringify({ vendor_ids: [pickA.value, pickB.value] }),
    })
    okMsg.value = `已合并为占位摊「${r.merged.name}」,宽 ${r.merged.stall_width_m} m;原两摊已标已合并退出`
    pickA.value = null
    pickB.value = null
    await refresh()
  } catch (e: any) {
    errMsg.value = errText(e)
  } finally {
    busy.value = false
  }
}

function badgeClass(s: string) {
  return s === 'active' ? 'badge badge-ok' : s === 'merged' ? 'badge badge-warn' : 'badge badge-bad'
}

onMounted(refresh)
</script>
<template>
  <h1>摊主队列</h1>
  <p class="sub">底部排队条 · 宽度与优先级 · 两个有效摊可一次提交合并为占位摊</p>

  <div class="card">
    <strong>合并占位</strong>
    <p class="muted" style="margin:0.3rem 0 0.6rem; font-size:0.8rem">
      选定两个仍有效摊主,合成一个新占位摊:宽 = 两摊宽度之和,优先级取较高者;原两摊标「已合并退出」。
    </p>
    <div style="display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap">
      <select v-model="pickA" class="ss-select">
        <option :value="null" disabled>选择摊主甲</option>
        <option v-for="r in activeRows" :key="'a' + r.id" :value="r.id" :disabled="r.id === pickB">
          {{ r.name }} · {{ r.stall_width_m }} m
        </option>
      </select>
      <span class="muted">＋</span>
      <select v-model="pickB" class="ss-select">
        <option :value="null" disabled>选择摊主乙</option>
        <option v-for="r in activeRows" :key="'b' + r.id" :value="r.id" :disabled="r.id === pickA">
          {{ r.name }} · {{ r.stall_width_m }} m
        </option>
      </select>
      <button class="btn" :disabled="!canMerge" @click="merge">合并占位</button>
    </div>
    <p v-if="okMsg" class="ss-flash-ok">{{ okMsg }}</p>
    <p v-if="errMsg" class="ss-flash-bad">{{ errMsg }}</p>
  </div>

  <div class="ss-vendor-queue" style="border-top:none; background:transparent; margin:0; padding:0.5rem 0 1rem">
    <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="ss-vendor-chip" :class="{ 'ss-chip-out': r.status !== 'active' }">
      <strong>{{ r.name }}</strong>
      <span v-if="r.status === 'active'">需 {{ r.stall_width_m }} m · 优先 {{ r.priority }}</span>
      <span v-else>{{ r.status_label }}</span>
    </div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>宽度(m)</th><th>优先级</th><th>状态</th><th>合并来源</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td>
          <td>{{ r.stall_width_m }}</td>
          <td>{{ r.priority }}</td>
          <td><span :class="badgeClass(r.status)">{{ r.status_label }}</span></td>
          <td class="muted">{{ (r.merged_from || []).map((x: any) => x.name).join(' + ') || '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
