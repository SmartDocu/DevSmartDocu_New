<style scoped>
.editor-container {
  display: flex;
  gap: 20px;
}

.editor-panel {
  width: 64%;
}

.editbutton{
  height: 465px !important;
}


.editor-root {
  border: 2px solid #4CAF50 !important;
  height: 500px !important;
  /* max-height: 800px !important; */
  padding: 16px;
  overflow-y: auto;
  background-color: white;
}

.variable-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 36%;
  padding-left: 16px;
}

.notice-box {
  background-color: #f9fbe7;
  margin-bottom: 10px;
  border-radius: 6px;
  color: #6a7d3c;
}

.buttons {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.btn-info,
.btn-primary {
  width: 75px;
  height: 35px;
  font-size: 16px;
  padding: 0px;
  cursor: pointer;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.results-container {
  height: 400px !important;
  overflow-y: auto !important;
}

.results-count {
  margin: 8px 0;
  font-weight: bold;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
  animation: fadeIn 0.2s ease forwards;
  opacity: 0;
}

.var-item {
  width: auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  border: 1px solid #ddd;
  border-radius: 6px;
  /* background-color: #f9f9f9; */
  margin-top: 5px;
}

.var-input label {
  font-weight: bold;
  color: #333;
}

.var-actions {
  display: flex;
  gap: 6px;
}
.var-actions button {
  font-size: 16px;
  background-color: transparent;
  border: none;
  cursor: pointer;
}

.no-results {
  color: #777;
  font-size: 14px;
  line-height: 1.6;
}

@keyframes fadeIn {
  to { opacity: 1; }
}/* 로딩 오버레이 스타일 */
.loading-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.5);
    display: none;
    justify-content: center;
    align-items: center;
    z-index: 9999;
  }

  .loading-content {
    background: white;
    padding: 30px;
    border-radius: 10px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    max-width: 300px;
  }

  /* 스피너 스타일 */
  .spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid #dc3545;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto 15px;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .loading-text {
    font-size: 16px;
    font-weight: bold;
    color: #333;
    margin-bottom: 10px;
  }

  .loading-subtext {
    font-size: 14px;
    color: #666;
  }

  /* 버튼 로딩 상태 */
  .btn-loading {
    position: relative;
    pointer-events: none;
    opacity: 0.7;
  }

  .btn-loading .btn-spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid #ffffff;
    border-radius: 50%;
    border-top-color: transparent;
    animation: spin 1s ease-in-out infinite;
    margin-right: 6px;
  }
</style>

<template>
  <div class="editor-container">
    <!-- 좌측: 에디터 -->
    <div class="editor-panel">
      <div ref="toolbarHost"></div>
      <div ref="editorContainer" class="editor-root" spellcheck="false"></div>
    </div>

    <!-- 우측: 변수/서식 패널 -->
    <div class="variable-list">
      <div class="notice-box">
        <p>＊반드시 저장 클릭 후 관리 페이지 이동 바랍니다.</p>
      </div>

      <div class="reader-section">
        <h2 class="section-title" style="margin-bottom: 9px; margin-top: 9px;">항목 추출</h2>

        <div id="btns" class="buttons" style="justify-content: center; gap: 15px;">
          <img :src="(window?.STATIC_URL || '/static/') + 'icons/extract.svg'"
              class="icon-img config-icon" @click="extractFormats" title="항목 추출" />
          <img :src="(window?.STATIC_URL || '/static/') + 'icons/save.svg'"
              class="icon-img config-icon" @click="saveToServer" title="항목 저장" />
        </div>

        <!-- 결과 목록 -->
        <div v-if="formats.length > 0" class="results-container" id="results-container">
          <div class="results-count">
            총 {{ formats.length }}개의 항목을 찾았습니다
          </div>

          <div
            v-for="(format, index) in formats"
            :key="format.objectUID || format.objectNm"
            class="result-item var-item"
            :style="{ animationDelay: `${index * 0.02}s` }"
          >
            <div class="var-input">
              <label class="format-label">{{ format.objectNm }}</label>
            </div>
            <div class="form-group-left" style="margin-bottom: 0px;">
              <div class="var-actions">
                <button title="해당 변수 수정 이동" @click="editToObjects({
                                                            chapteruid: format.chapterUID, 
                                                            objectuid: format.objectUID, 
                                                            objecttypecd: format.objectTypeCd, 
                                                            objectnm: format.objectNm})"
                  class="icon-btn"
                  :disabled="!format.objectUID || format.objectUID === ''"
                  :style="{
                    cursor: !format.objectUID ? 'not-allowed' : 'pointer'
                  }">
                  <img :src="(window?.STATIC_URL || '/static/') + 'icons/edit.svg'"
                    class="icon-img"/>
                </button>
              </div>
              <div class="var-actions">
                <button title="해당 변수 설정 이동" @click="moveToObjects({
                                                            chapteruid: format.chapterUID, 
                                                            objectuid: format.objectUID})"
                  class="icon-btn"
                  :disabled="!format.objectUID || format.objectUID === ''"
                  :style="{
                    cursor: !format.objectUID ? 'not-allowed' : 'pointer'
                  }">
                  <img :src="(window?.STATIC_URL || '/static/') + 'icons/configuration.svg'"
                    class="icon-img" />
              </button>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="no-results">
          에디터에 <code>{{ '{' + '{명칭}' + '}' }}</code> 형태로 입력한 후<br />
          <strong>읽기</strong> 버튼을 클릭하세요
        </div>
      </div>
    </div>
  </div>


<!-- 로딩 오버레이 -->
<div id="save_loadingOverlay" class="loading-overlay">
  <div class="loading-content">
    <div class="spinner"></div>
    <div class="loading-text">데이터 저장 중...</div>
    <div class="loading-subtext">잠시만 기다려 주세요.</div>
  </div>
</div>

<!-- 로딩 오버레이 -->
<div id="read_loadingOverlay" class="loading-overlay">
  <div class="loading-content">
    <div class="spinner"></div>
    <div class="loading-text">서식 읽는 중...</div>
    <div class="loading-subtext">잠시만 기다려 주세요.</div>
  </div>
</div>
</template>

<script setup>
/**
 * Vue 3 + CKEditor5 DecoupledEditor 리팩토링
 * - DOM 조작 제거 (Vue 방식 상태 렌더링)
 * - {{}} 추출 → formats[]에 저장 후 우측 label로 나열
 * - 변수 동기화/삭제/강조를 모델 전체 순회(createRangeIn) 방식으로 구현
 * - onBeforeUnmount에서 destroy
 */
import { ref, onMounted, watch, toRaw, markRaw } from 'vue'
import axios from 'axios'

// 로딩 상태 관리 함수들
function save_showLoading() {
  const overlay = document.getElementById('save_loadingOverlay');
  const btn = document.getElementById('saveBtn');
  
  // 오버레이 표시
  overlay.style.display = 'flex';
  
  // 버튼 로딩 상태로 변경
  if (btn) {
    btn.classList.add('btn-loading');
    btn.innerHTML = '<span class="btn-spinner"></span>저장 중...';
    btn.disabled = true;
  }
}

function save_hideLoading() {
  const overlay = document.getElementById('save_loadingOverlay');
  const btn = document.getElementById('saveBtn');
  
  // 오버레이 숨기기
  overlay.style.display = 'none';
  
  // 버튼 원래 상태로 복원
  if (btn) {
    btn.classList.remove('btn-loading');
    btn.innerHTML = '저장';
    btn.disabled = false;
  }
}

// 로딩 상태 관리 함수들
function read_showLoading() {
  const overlay = document.getElementById('read_loadingOverlay');
  const btn = document.getElementById('readBtn');
  
  // 오버레이 표시
  overlay.style.display = 'flex';
  
  // 버튼 로딩 상태로 변경
  if (btn) {
    btn.classList.add('btn-loading');
    btn.innerHTML = '<span class="btn-spinner"></span>읽는 중...';
    btn.disabled = true;
  }
}

function read_hideLoading() {
  const overlay = document.getElementById('read_loadingOverlay');
  const btn = document.getElementById('readBtn');
  
  // 오버레이 숨기기
  overlay.style.display = 'none';
  
  // 버튼 원래 상태로 복원
  if (btn) {
    btn.classList.remove('btn-loading');
    btn.innerHTML = '읽기';
    btn.disabled = false;
  }
}

// ✅ props 정의
const props = defineProps({
  html_content: {
    type: String,
    default: '<p>기본 문서입니다.</p>'
  },
  Objects: {                // DB에서 불러온 object 목록
    type: Array,
    default: () => []       // [{ objectUID, objectNm }]
  },
  docid: {
    type: String,
    required: true
  },
  ChapterUID: {
    type: String,
    required: true
  },
  ChapterNm: {
    type: String,
    required: true
  },
  editbuttonyn: {
    type: String,
    required: true
  }
})

// =====================
// 서버 저장
// =====================
const saveToServer = async () => {
  save_showLoading()
  try {
    await axios.post('/api/save_chapter_objects/', {
      html_content: editorData.value,
      ChapterUID: props.ChapterUID,
      formats: formats.value,
      variables: { ...variables.value }
    })
    save_hideLoading()
    alert(`문서 양식: '${props.ChapterNm}' 저장되었습니다.`)
    location.reload()
  } catch (err) {
    console.error(err)
    save_hideLoading()
    // 서버가 보낸 메시지
    const msg =
      err.response?.data?.message ||
      err.response?.data?.error ||
      err.message ||
      "알 수 없는 오류"
    const add =
      err.response?.data?.add||
      ""

    alert(`저장 실패: ${msg}\n${add}`)
    location.reload()
  }
}


// 화면 이동
const editToObjects = async (payload) => {
  const chapteruid = payload.chapteruid
  const objectuid = payload.objectuid
  const objecttypecd = payload.objecttypecd
  const objectnm = payload.objectnm

  sessionStorage.setItem('chapter_template_chapteruid', chapteruid)
  
  const enc_objectnm = encodeURIComponent(objectnm)

  let url = "";
  let ok = true
  if (["TU"].includes(objecttypecd)){
    url = `/master/tables/?chapteruid=${chapteruid}&objectnm=${enc_objectnm}`;
  } 
  else if (["CU"].includes(objecttypecd)){
    url = `/master/charts/?chapteruid=${chapteruid}&objectnm=${enc_objectnm}`;
  } 
  else if (["SU"].includes(objecttypecd)){
    url = `/master/sentences/?chapteruid=${chapteruid}&objectnm=${enc_objectnm}`;
  } 
  else if (["TA"].includes(objecttypecd)){
    url = `/master/ai_tables/?chapteruid=${chapteruid}&objectnm=${enc_objectnm}`;
  }
  else if (["CA"].includes(objecttypecd)){
    url = `/master/ai_charts/?chapteruid=${chapteruid}&objectnm=${enc_objectnm}`;
  }
  else if (["SA"].includes(objecttypecd)){
    url = `/master/ai_sentences/?chapteruid=${chapteruid}&objectnm=${enc_objectnm}`;
  } else {
    alert('현재 설정된 것이 없습니다.');
    ok = false;
  }
  // console.log(url)
  // window.open(url);
  if (ok){
    location.href = url
  }
  
}

const moveToObjects = async (payload) => {
  const chapteruid = payload.chapteruid
  const objectuid = payload.objectuid

  const returnUrl = encodeURIComponent(window.location.href);

  const baseUrl = window.djangoUrls?.masterObject || '/master/object/';
  const url = `${baseUrl}?chapteruid=${chapteruid}&objectuid=${objectuid}`;
  // window.open(url);
  location.href = url
}

// =====================
// State
// =====================
const editorContainer = ref(null)
const toolbarHost = ref(null)
const editorInstance = ref(null)
const isEditorReady = ref(false)

const editorData = ref(props.html_content || '<p>자유롭게 양식을 설정 하십시요.</p>')
const variables = ref({})
const formats = ref([])  // [{ objectUID, objectNm }]


// ----------------------
// Helpers
// ----------------------
const initFormatsFromDB = () => {
  const cleaned = (props.Objects || [])
    .filter(o => o?.objectNm && o.objectNm.trim() !== '')
    .map(o => ({
      objectUID: o.objectUID ?? null,
      objectNm: o.objectNm.trim(),
      objectTypeCd: o.objectTypeCd.trim(),
      chapterUID: o.chapterUID.trim()
    }))
  formats.value = sortFormats(cleaned)
}

const sortFormats = (arr) => {
  return [...arr].sort((a, b) => a.objectNm.localeCompare(b.objectNm, 'ko'))
}

// 신규 objectNm 배열을 기존 formats에 합치고 정렬해서 돌려주는 함수
const mergeAndSortFormats = (existing, newNames) => {
  const existingSet = new Set(existing.map(f => f.objectNm))
  const merged = [...existing]

  for (const nm of newNames) {
    if (!existingSet.has(nm)) {
      merged.push({
        objectUID: null,   // 신규
        objectNm: nm
      })
      existingSet.add(nm)
    }
  }
  return sortFormats(merged)
}

// 안전하게 {{}} 안에서 문자열을 정제
const cleanPatternName = (raw) => {
  return raw
    ?.replace(/<[^>]*>/g, '')    // HTML 태그 제거
    .replace(/&nbsp;/gi, '')     // nbsp 제거
    .trim()
}

// ----------------------
// {{}} 패턴 읽기 → 신규만 합쳐서 정렬 유지
// ----------------------
const extractFormats = () => {
  if (!isEditorReady.value || !editorInstance.value) {
    alert('에디터가 아직 로드되지 않았습니다.')
    return
  }
  read_showLoading()
  console.log('추출')
  const data = editorInstance.value.getData()
  const regex = /\{\{([^}]+)\}\}/g
  const matches = [...data.matchAll(regex)]

  const newNames = []
  for (const m of matches) {
    const cleaned = cleanPatternName(m[1])
    if (cleaned) newNames.push(cleaned)
  }

  // 중복 제거
  const uniqueNames = [...new Set(newNames)]

  // ✅ 기존 순서 유지: 가나다 정렬 제거
  formats.value = uniqueNames.map(nm => {
    const existing = formats.value.find(f => f.objectNm === nm)
    // console.log(existing)
    return {
      objectUID: existing?.objectUID ?? null,
      objectNm: nm,
      chapterUID: existing?.chapterUID ?? null,
      objecttypecd: existing?.objectTypeCd ?? null,
    }
  }) 

  read_hideLoading()  
}



// =====================
// CKEditor 초기화
// =====================
onMounted(async () => {
  // 1) DB objects → formats 초기화 & 정렬
  // initFormatsFromDB()
  // 초기화: DB에서 불러온 objects를 formats에 반영
  if (props.Objects.length > 0) {
    formats.value = props.Objects.map(o => ({
      objectUID: o.objectuid ?? null,
      objectNm: o.objectnm?.trim() ?? '',
      objectTypeCd: o.objecttypecd.trim(),
      chapterUID: o.chapteruid.trim()
    })).sort((a, b) => (b.orderno ?? 0) - (a.orderno ?? 0))
    // => a.objectNm.localeCompare(b.objectNm, 'ko'))
  }
  // console.log('Formats: ', formats.value)

  // 2) CKEditor 초기화
  initEditor()

  const btns = document.getElementById('btns')
  const results_list = document.getElementById("results-container");
  // 3) 추출 및 저장 버튼 숨김
  if (props.editbuttonyn == 'N'){
    
    btns.hidden = true;
    btns.style.display = 'none';
  }
})

// **props.Objects 변화 감지**
watch(
  () => props.Objects,
  (newVal) => {
    if (newVal && newVal.length > 0) {
      initFormatsFromDB()
    }
  },
  { immediate: true }
)

const initEditor = async () => {
  try {
    const editor = await window.DecoupledEditor.create(editorContainer.value, {
    // const editor = await DecoupledEditor.create(editorContainer.value, {
      extraPlugins: [VariablePlugin],
      htmlSupport: {
        allow: [{ name: /.*/, attributes: true, classes: true, styles: true }]
      },
      htmlEmbed: { showPreviews: true },
      toolbar: {
        items: [
          'pageBreak', '|',   // <-- 여기 추가
          'fontSize', '|',
          'bold', 'italic', 'underline', 'strikethrough', '|',
          'fontColor', 'fontBackgroundColor', '|',
          'alignment', '|',
          'outdent', 'indent', '|',
          'insertTable', 'blockQuote', '|',
          'undo', 'redo', '|'
        ]
      },
      language: 'ko',
      table: { contentToolbar: ['tableColumn', 'tableRow', 'mergeTableCells'] },
      heading: {
        options: [
          { model: 'paragraph', title: '본문', class: 'ck-heading_paragraph' },
          { model: 'heading1', view: 'h1', title: '제목 1', class: 'ck-heading_heading1' },
          { model: 'heading2', view: 'h2', title: '제목 2', class: 'ck-heading_heading2' },
          { model: 'heading3', view: 'h3', title: '제목 3', class: 'ck-heading_heading3' },
          { model: 'heading4', view: 'h4', title: '제목 4', class: 'ck-heading_heading4' }
        ]
      },
      fontSize: {
        options: [9, 10, 11, 13, 14, 16, 20, 24, 28],
        supportAllValues: true
      },
      fontFamily: {
        options: ['굴림체, GulimChe, sans-serif'],
        supportAllValues: true,
        default: '굴림체, GulimChe, sans-serif'
      }
    })

    // 툴바 위치 이동 (필요시)
    if (toolbarHost.value) {
      toolbarHost.value.appendChild(editor.ui.view.toolbar.element)
    }

    editorInstance.value = markRaw(editor)

    await new Promise(resolve => {
      if (editor.state === 'ready') resolve()
      else editor.once('ready', resolve)
    })

    editor.setData(editorData.value)
    isEditorReady.value = true

    editor.model.document.on('change:data', () => {
      editorData.value = editor.getData()
      syncFromEditor()
    })
  } catch (e) {
    console.error('에디터 초기화 실패:', e)
  }
}

// ----------------------
// variables 동기화 (에디터 내부 variable attr 텍스트 수집)
// ----------------------
const syncFromEditor = () => {
  if (!editorInstance.value) return
  const editor = toRaw(editorInstance.value)
  const root = editor.model.document.getRoot()

  const newVars = {}
  const range = editor.model.createRangeIn(root)
  for (const { item } of range.getWalker()) {
    if (item.is('$text') && item.hasAttribute('variable')) {
      const key = item.getAttribute('variable')
      newVars[key] = item.data
    }
  }
  variables.value = newVars
}

// ----------------------
// CKEditor Variable Plugin
// ----------------------
function VariablePlugin(editor) {
  editor.model.schema.extend('$text', { allowAttributes: ['variable'] })

  editor.conversion.for('upcast').elementToAttribute({
    view: { name: 'span', classes: /.+/ },
    model: {
      key: 'variable',
      value: viewElement => {
        const classes = [...viewElement.getClassNames()]
        return classes[0] || null
      }
    }
  })

  editor.conversion.for('downcast').attributeToElement({
    model: 'variable',
    view: (modelAttrValue, { writer }) => {
      if (!modelAttrValue) return null
      return writer.createAttributeElement('span', { class: modelAttrValue }, { priority: 5 })
    }
  })
}
</script>