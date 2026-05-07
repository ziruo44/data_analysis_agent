<template>
  <div class="file-selector">
    <select :value="selectedFile" @change="onSelect">
      <option value="">选择数据文件</option>
      <option v-for="f in files" :key="f" :value="`storage/${f}`">{{ f }}</option>
    </select>
    <label class="upload-btn">
      上传 CSV
      <input type="file" accept=".csv" @change="onUpload">
    </label>
  </div>
</template>

<script setup>
defineProps({
  files: { type: Array, default: () => [] },
  selectedFile: { type: String, default: '' },
})

const emit = defineEmits(['select', 'upload'])

const onSelect = (e) => {
  emit('select', e.target.value)
}

const onUpload = (e) => {
  const file = e.target.files[0]
  if (!file) return
  emit('upload', file)
  e.target.value = ''
}
</script>
