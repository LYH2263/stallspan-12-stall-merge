<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const pickA = ref<number | null>(null)
const pickB = ref<number | null>(null)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const active = computed(() => rows.value.filter(r => r.status === 'active'))
const retired = computed(() => rows.value.filter(r => r.status !== 'active'))
async function load() { rows.value = await api('/vendors') }
function detailOf(e: any): string {
  try { return JSON.parse(e.message).detail || e.message } catch { return e.message || '合并失败' }
}
async function merge() {
  error.value = ''; notice.value = ''
  if (!pickA.value || !pickB.value || pickA.value === pickB.value) {
    error.value = '请选择两个不同的仍有效摊主'
    return
  }
  busy.value = true
  try {
    const res = await api('/vendors/merge', {
      method: 'POST',
      body: JSON.stringify({ vendor_id_a: pickA.value, vendor_id_b: pickB.value }),
    })
    notice.value = `已合成占位摊「${res.merged.name}」 · 宽 ${res.merged.stall_width_m} m · 优先 ${res.merged.priority}，随后现算或确认开间生效`
    pickA.value = null; pickB.value = null
    await load()
  } catch (e: any) {
    error.value = detailOf(e)
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>
<template>
  <h1>摊主队列</h1>
  <p class="sub">底部排队条 · 宽度与优先级 · 可一次提交合并两个仍有效摊主</p>
  <div class="ss-vendor-queue" style="border-top:none; background:transparent; margin:0; padding:0.5rem 0 1rem">
    <div v-for="r in active" :key="r.id" class="ss-vendor-chip">
      <strong>{{ r.name }}</strong>
      <span>需 {{ r.stall_width_m }} m · 优先 {{ r.priority }}</span>
    </div>
    <div v-for="r in retired" :key="r.id" class="ss-vendor-chip ss-chip-merged">
      <strong>{{ r.name }}</strong>
      <span class="badge badge-warn">已合并退出</span>
    </div>
  </div>
  <div class="card ss-merge-bar">
    <strong>合并占位</strong>
    <select v-model="pickA">
      <option :value="null" disabled>摊主甲</option>
      <option v-for="r in active" :key="'a' + r.id" :value="r.id">{{ r.name }} · {{ r.stall_width_m }} m</option>
    </select>
    <span class="muted">＋</span>
    <select v-model="pickB">
      <option :value="null" disabled>摊主乙</option>
      <option v-for="r in active" :key="'b' + r.id" :value="r.id">{{ r.name }} · {{ r.stall_width_m }} m</option>
    </select>
    <button class="btn" :disabled="busy" @click="merge">合并占位</button>
    <span class="muted">宽为两摊之和 · 优先取较高者 · 确认开间才落库</span>
  </div>
  <p v-if="error" class="ss-error">{{ error }}</p>
  <p v-if="notice" class="ss-notice">{{ notice }}</p>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>宽度(m)</th><th>优先级</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id" :class="{ 'ss-row-merged': r.status !== 'active' }">
          <td>{{ r.name }}</td><td>{{ r.stall_width_m }}</td><td>{{ r.priority }}</td>
          <td><span v-if="r.status === 'active'" class="badge badge-ok">有效</span>
              <span v-else class="badge badge-warn">已合并退出</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
