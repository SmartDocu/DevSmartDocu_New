
<style scoped>
.helps-container {
  display: flex;
  gap: 20px;
  height: calc(100vh - 200px);
  min-height: 600px;
}

/* 좌측 패널 */
.helps-list-panel {
  width: 25%;
  min-width: 250px;
  display: flex;
  flex-direction: column;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid #ddd;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.btn-new {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #4CAF50;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.btn-new:hover {
  background: #45a049;
}

.helps-cards {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.help-card {
  padding: 12px;
  margin-bottom: 8px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.help-card:hover {
  background: #f5f5f5;
  border-color: #4CAF50;
}

.help-card.active {
  background: #e8f5e9;
  border-color: #4CAF50;
  box-shadow: 0 2px 4px rgba(76, 175, 80, 0.2);
}

.help-card-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}

.help-card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #666;
}

.no-helps {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

/* 중앙 패널 (에디터) */
.editor-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
}

.editor-root {
  flex: 1;
  border: 2px solid #4CAF50;
  border-radius: 0 0 8px 8px;
  padding: 16px;
  overflow-y: auto;
  background: white;
  min-height: 400px;
  width: 985px;
}

/* 우측 패널 (폼) */
.form-panel {
  width: 25%;
  min-width: 250px;
  display: flex;
  flex-direction: column;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
}

.form-content {
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.form-input {
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.form-input:focus {
  outline: none;
  border-color: #4CAF50;
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

.form-actions .icon-btn {
  flex: 1; /* 👈 각 버튼이 동일한 비율로 확장 */
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-save,
.btn-delete {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
}

.btn-save {
  background: #4CAF50;
  color: white;
}

.btn-save:hover:not(:disabled) {
  background: #45a049;
}

.btn-delete {
  background: #f44336;
  color: white;
}

.btn-delete:hover:not(:disabled) {
  background: #da190b;
}

.btn-save:disabled,
.btn-delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 로딩 오버레이 */
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

.spinner {
  border: 4px solid #f3f3f3;
  border-top: 4px solid #4CAF50;
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
</style>
<template>
  <div class="helps-container">
    <!-- 좌측: Helps 리스트 -->
    <div class="helps-list-panel">
      <div class="panel-header">
        <h2>도움말 목록</h2>
      </div>
      
      <div class="helps-cards">
        <div 
          v-for="help in helps" 
          :key="help.helpuid"
          :class="['help-card', { active: selectedHelp?.helpuid === help.helpuid }]"
          @click="selectHelp(help)"
        >
          <div class="help-card-title">{{ help.help || '제목 없음' }}</div>
          <div class="help-card-meta">
            <span class="help-card-date">
              {{ formatDate(help.createdts) }}
            </span>
            <span class="help-card-author">{{ help.createuser }}</span>
          </div>
        </div>
        
        <div v-if="helps.length === 0" class="no-helps">
          등록된 도움말이 없습니다.
        </div>
      </div>
    </div>

    <!-- 중앙: CKEditor -->
    <div class="editor-panel">
      <div class="panel-header">
        <h2>내용 편집</h2>
      </div>
      
      <div ref="toolbarHost"></div>
      <div ref="editorContainer" class="editor-root" spellcheck="false"></div>
    </div>

    <!-- 우측: 입력 폼 -->
    <div class="form-panel">
      <div class="panel-header">
        <h2>상세 정보</h2>
      </div>
      
      <div class="form-content">
        <div class="form-group">
          <label for="help-title">제목</label>
          <input 
            id="help-title"
            v-model="formData.help" 
            type="text" 
            placeholder="도움말 제목을 입력하세요"
            class="form-input"
          />
        </div>

        <div class="form-group">
          <label for="help-url">URL</label>
          <input 
            id="help-url"
            v-model="formData.url" 
            type="text" 
            placeholder="관련 URL을 입력하세요"
            class="form-input"
          />
        </div>

        <div class="form-actions">
          <button id="new-btn" type="button" class="icon-btn" @click="createNewHelp">
            <div class="icon-wrapper">
              <img :src="(window?.STATIC_URL || '/static/') + 'icons/new.svg'" class="icon-img new-icon" title="신규">
              <span class="icon-label">신규</span>
            </div>
          </button>
          <button id="save-btn" type="button" class="icon-btn" @click="saveHelp">
            <div class="icon-wrapper">
              <img :src="(window?.STATIC_URL || '/static/') + 'icons/save.svg'" class="icon-img save-icon" title="저장">
              <span class="icon-label">저장</span>
            </div>
          </button>
          <button id="delete-btn" type="button" class="icon-btn" @click="deleteHelp">
            <div class="icon-wrapper">
              <img :src="(window?.STATIC_URL || '/static/') + 'icons/delete.svg'" class="icon-img del-icon" title="삭제">
              <span class="icon-label">삭제</span>
            </div>
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- 로딩 오버레이 -->
  <div id="loadingOverlay" class="loading-overlay">
    <div class="loading-content">
      <div class="spinner"></div>
      <div class="loading-text">처리 중...</div>
      <div class="loading-subtext">잠시만 기다려 주세요.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, toRaw, markRaw } from 'vue'
import axios from 'axios'

// Props
const props = defineProps({
  helps: {
    type: Array,
    default: () => []
  }
})

const getCsrfToken = () => {
  const name = 'csrftoken'
  const cookies = document.cookie.split(';')
  for (let cookie of cookies) {
    const [key, value] = cookie.trim().split('=')
    if (key === name) return value
  }
  return null
}

// State
const helps = ref([...props.helps])
const selectedHelp = ref(null)
const formData = ref({
  help: '',
  url: '',
  desc: ''
})

const editorContainer = ref(null)
const toolbarHost = ref(null)
const editorInstance = ref(null)
const isEditorReady = ref(false)

// 날짜 포맷팅
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('ko-KR', { 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 도움말 선택
const selectHelp = (help) => {
  selectedHelp.value = help
  formData.value = {
    help: help.help || '',
    url: help.url || '',
    desc: help.desc || ''
  }
  
  // 에디터에 내용 설정
  if (isEditorReady.value && editorInstance.value) {
    editorInstance.value.setData(help.desc || '<p></p>')
  }
}

// 새 도움말 생성
const createNewHelp = () => {
  selectedHelp.value = null
  formData.value = {
    help: '',
    url: '',
    desc: ''
  }
  
  // 에디터 내용도 초기화
  if (isEditorReady.value && editorInstance.value) {
    editorInstance.value.setData('<p></p>')
  }

  // const newHelp = {
  //   helpuid: null,
  //   help: '새 도움말',
  //   url: '',
  //   desc: '<p></p>',
  //   creator: '현재 사용자',
  //   createdts: new Date().toISOString()
  // }
  
  // helps.value.unshift(newHelp)
  // selectHelp(newHelp)
}

// 저장
const saveHelp = async () => {
  // if (!selectedHelp.value) return
  
  if (!formData.value.help || !formData.value.help.trim()) {
    alert('제목을 입력해주세요.')
    return
  }

  if (!formData.value.url || !formData.value.url.trim()) {
    alert('URL을 입력해주세요.')
    return
  }

  showLoading()
  
  try {
    const editorContent = isEditorReady.value && editorInstance.value 
      ? editorInstance.value.getData() 
      : formData.value.desc

    // HTML에서 Base64 이미지 추출
    const parser = new DOMParser();
    const doc = parser.parseFromString(editorContent, 'text/html');
    const images = doc.querySelectorAll('img[src^="data:image"]');

    const imageData = [];
    images.forEach((img, index) => {
      const src = img.getAttribute('src');
      const matches = src.match(/^data:(image\/\w+);base64,(.+)$/);
      
      if (matches) {
        const mimeType = matches[1];  // image/png, image/jpeg 등
        const base64Data = matches[2];  // Base64 문자열
        
        imageData.push({
          index: index,
          mimeType: mimeType,
          base64: base64Data,
          alt: img.getAttribute('alt') || '',
          width: img.getAttribute('width') || '',
          height: img.getAttribute('height') || ''
        });
      }
    });

    const payload = {
      helpuid: selectedHelp.value?.helpuid || null,
      help: formData.value.help,
      url: formData.value.url,
      desc: editorContent,
    }

    //images: imageData

    const response = await axios.post('/master/help_save/', payload, {
      headers: {
        'X-CSRFToken': getCsrfToken()
      }
    })
    
    hideLoading()
    
    if (response.data.success) {
      alert('저장되었습니다.')
      // console.log(response.data)

      window.location.reload()
      // 목록 업데이트
      // if (!selectedHelp.value) {
      //   console.log('선택 uid 가 없다??')
      //   const newHelp = {
      //     helpuid: response.data.helpuid,
      //     help: formData.value.help,
      //     url: formData.value.url,
      //     desc: editorContent,
      //     creator: response.data.creator,
      //     createdts: response.data.createdts
      //   }
      //   console.log('값 삽입')
      //   console.log(newHelp)
      //   selectHelp(newHelp)
      // }
      
      // const index = helps.value.findIndex(h => 
      //   h.helpuid === selectedHelp.value.helpuid || h === selectedHelp.value
      // )

      // console.log(index)
      
      // if (index !== -1) {
      //   helps.value[index] = {
      //     ...selectedHelp.value,
      //     // ...payload,
      //     help: formData.value.help,
      //     url: formData.value.url,
      //     desc: editorContent,
      //     helpuid: response.data.helpuid || selectedHelp.value.helpuid
      //   }
      // }
      
      // selectHelp(helps.value[index])
    }
  } catch (err) {
    hideLoading()
    console.error(err)
    alert('저장 실패: ' + (err.response?.data?.message || err.message))
  }
}

// 삭제
const deleteHelp = async () => {
  if (!selectedHelp.value?.helpuid) return
  
  if (!confirm('정말 삭제하시겠습니까?')) return
  
  showLoading()
  
  try {

    await axios.post('/master/help_delete/', {
      helpuid: selectedHelp.value.helpuid
    },{
      headers: {
        'X-CSRFToken': getCsrfToken()
      }
    })
    
    hideLoading()
    alert('삭제되었습니다.')
    
    window.location.reload()

    // helps.value = helps.value.filter(h => h.helpuid !== selectedHelp.value.helpuid)
    
    // selectedHelp.value = null
    // formData.value = { help: '', url: '', desc: '' }
    
    // if (isEditorReady.value && editorInstance.value) {
    //   editorInstance.value.setData('<p></p>')
    // }
  } catch (err) {
    hideLoading()
    console.error(err)
    alert('삭제 실패: ' + (err.response?.data?.message || err.message))
  }
}

// 로딩 관리
const showLoading = () => {
  const overlay = document.getElementById('loadingOverlay')
  if (overlay) overlay.style.display = 'flex'
}

const hideLoading = () => {
  const overlay = document.getElementById('loadingOverlay')
  if (overlay) overlay.style.display = 'none'
}


// 커스텀 업로드 어댑터 - Base64로 변환하여 img 태그 삽입
class Base64UploadAdapter {
  constructor(loader) {
    this.loader = loader;
  }

  upload() {
    return this.loader.file.then(file => new Promise((resolve, reject) => {
      const reader = new FileReader();

      reader.onload = () => {
        // Base64 데이터 (data:image/png;base64,iVBORw0KG...)
        const base64Data = reader.result;
        
        resolve({
          default: base64Data  // 👈 CKEditor가 <img src="data:image/png;base64,..."> 형태로 삽입
        });
      };

      reader.onerror = error => reject(error);
      reader.readAsDataURL(file);  // 👈 Base64로 변환
    }));
  }

  abort() {}
}

function Base64UploadAdapterPlugin(editor) {
  editor.plugins.get('FileRepository').createUploadAdapter = (loader) => {
    return new Base64UploadAdapter(loader);
  };
}


// CKEditor 초기화
const initEditor = async () => {
  try {
    const editor = await window.DecoupledEditor.create(editorContainer.value, {
      extraPlugins: [Base64UploadAdapterPlugin],
      htmlSupport: {
        allow: [{ name: /.*/, attributes: true, classes: true, styles: true }]
      },
      toolbar: {
        items: [
          'heading', '|',
          'fontSize', 'fontColor', 'fontBackgroundColor', '|',
          'bold', 'italic', 'underline', 'strikethrough', '|',
          'alignment', '|',
          'bulletedList', 'numberedList', '|',
          'outdent', 'indent', '|',
          'link', 'uploadImage', 'insertTable', 'blockQuote', '|',
          'undo', 'redo'
        ]
      },
      language: 'ko',
      fontSize: {
        options: [9, 10, 11, 13, 14, 16, 20, 24, 28],
        supportAllValues: true
      }
    })

    if (toolbarHost.value) {
      toolbarHost.value.appendChild(editor.ui.view.toolbar.element)
    }

    editorInstance.value = markRaw(editor)

    await new Promise(resolve => {
      if (editor.state === 'ready') resolve()
      else editor.once('ready', resolve)
    })

    isEditorReady.value = true

    editor.model.document.on('change:data', () => {
      formData.value.desc = editor.getData()
    })
  } catch (e) {
    console.error('에디터 초기화 실패:', e)
  }
}

// Mount
onMounted(() => {
  initEditor()
})
</script>
