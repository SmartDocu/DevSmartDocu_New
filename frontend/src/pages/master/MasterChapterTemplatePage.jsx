import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { App, Spin, Select, Modal } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

// ──────────────────────────────────────────────
// objecttypecd → React 라우트 매핑
// ──────────────────────────────────────────────
const TYPE_ROUTE = {
  TU: '/master/tables',
  CU: '/master/charts',
  SU: '/master/sentences',
  TA: '/master/ai-tables',
  CA: '/master/ai-charts',
  SA: '/master/ai-sentences',
}

// ══════════════════════════════════════════════
// CKEditor5 커스텀 플러그인 (Vue 버전 완전 이식)
// ══════════════════════════════════════════════

function VariablePlugin(editor) {
  editor.model.schema.extend('$text', { allowAttributes: ['variable'] })

  editor.conversion.for('upcast').elementToAttribute({
    view: { name: 'span', classes: /.+/ },
    model: {
      key: 'variable',
      value: viewElement => {
        const classes = [...viewElement.getClassNames()]
        return classes[0] || null
      },
    },
  })

  editor.conversion.for('downcast').attributeToElement({
    model: 'variable',
    view: (modelAttrValue, { writer }) => {
      if (!modelAttrValue) return null
      return writer.createAttributeElement('span', { class: modelAttrValue }, { priority: 5 })
    },
  })
}

function TemplateBlockPlugin(editor) {
  const TEMPLATE_BLOCKS = [
    {
      id: 'insertIfElse',
      label: 'IF',
      lines: ['{{#if}}', '  ', '{{#ELSE}}', '  ', '{{#END if}}'],
    },
    {
      id: 'insertFor',
      label: 'Fo',
      lines: ['{{#FOR}}', '  ', '{{#END FOR}}'],
    },
  ]

  TEMPLATE_BLOCKS.forEach(({ id, label, lines }) => {
    editor.ui.componentFactory.add(id, () => {
      const view = {
        element: null,
        render() {
          const btn = document.createElement('button')
          btn.type = 'button'
          btn.className = 'ck ck-button ck-template-block-btn'
          btn.textContent = label
          btn.title = label
          btn.style.cssText = `
            font-size: 14px;
            font-weight: bold;
            padding: 4px 8px;
            white-space: nowrap;
            cursor: pointer;
          `
          btn.addEventListener('mousedown', (e) => {
            e.preventDefault()
            editor.model.change(writer => {
              const position = editor.model.document.selection.getFirstPosition()
              const fragment = writer.createDocumentFragment()
              lines.forEach(line => {
                const para = writer.createElement('paragraph')
                const isEmptyLine = line.trim() === ''
                if (isEmptyLine) {
                  writer.appendText(line, para)
                } else {
                  writer.appendText(line, { fontBackgroundColor: 'hsl(25, 90%, 85%)' }, para)
                }
                writer.append(para, fragment)
              })
              editor.model.insertContent(fragment, position)
            })
            editor.editing.view.focus()
          })
          this.element = btn
          return btn
        },
        destroy() {},
      }
      view.render()
      return view
    })
  })
}

function AutoCompletePlugin(editor, tbl_params_ref, sca_params_ref) {
  let dropdown = null

  const TRIGGERS = [
    {
      keyword: 'For',
      options: [
        {
          label: '🔁 FOR ... END FOR',
          lines: ['{{#FOR}}', '  ', '{{#END FOR}}'],
          color: 'hsl(25, 90%, 85%)',
        },
      ],
    },
    {
      keyword: 'If',
      options: [
        {
          label: '🔀 IF ... ELSE ... END IF',
          lines: ['{{#if}}', '  ', '{{#ELSE}}', '  ', '{{#END if}}'],
          color: 'hsl(25, 90%, 85%)',
        },
      ],
    },
    { keyword: '{{#FOR', type: 'tbl_params' },
    { keyword: '{{#if', type: 'if_params' },
  ]

  const removeDropdown = () => {
    if (dropdown) { dropdown.remove(); dropdown = null }
  }

  const findCurrentForParamnm = () => {
    const pos = editor.model.document.selection.getFirstPosition()
    if (!pos) return null
    const root = editor.model.document.getRoot()
    const children = [...root.getChildren()]
    let currentIndex = -1
    for (let i = 0; i < children.length; i++) {
      if (children[i] === pos.parent) { currentIndex = i; break }
    }
    let forSkip = 0
    for (let i = currentIndex; i >= 0; i--) {
      let lineText = ''
      for (const node of children[i].getChildren()) {
        if (node.is('$text')) lineText += node.data
      }
      if (lineText.includes('{{#END FOR}}')) { forSkip++; continue }
      const forMatch = lineText.match(/\{\{#FOR\s+@([^\}\s]+)\}\}/)
      if (forMatch) {
        if (forSkip > 0) { forSkip--; continue }
        return forMatch[1].trim()
      }
    }
    return null
  }

  const showColumnsDropdown = (columns) => {
    removeDropdown()
    const domSelection = window.getSelection()
    if (!domSelection.rangeCount) return
    const rect = domSelection.getRangeAt(0).getBoundingClientRect()

    dropdown = document.createElement('div')
    dropdown.style.cssText = `
      position: fixed; top: ${rect.bottom + 6}px; left: ${rect.left}px;
      background: white; border: 1px solid #ccc; border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999;
      min-width: 200px; max-height: 250px; overflow-y: auto;
    `
    const header = document.createElement('div')
    header.textContent = '📋 컬럼 선택'
    header.style.cssText = `padding: 8px 12px; font-size: 12px; font-weight: bold; color: #555;
      background: #f7f7f7; border-bottom: 1px solid #eee; position: sticky; top: 0;`
    dropdown.appendChild(header)

    ;[...columns, 'count(*)'].forEach(col => {
      const item = document.createElement('div')
      item.textContent = col
      item.style.cssText = `padding: 8px 14px; cursor: pointer; font-size: 13px;
        border-bottom: 1px solid #f0f0f0; transition: background 0.1s;`
      if (col === 'count(*)') { item.style.fontWeight = 'bold'; item.style.color = '#5c8a5c' }
      item.addEventListener('mouseenter', () => (item.style.background = '#f0f7ff'))
      item.addEventListener('mouseleave', () => (item.style.background = ''))
      item.addEventListener('mousedown', (e) => {
        e.preventDefault()
        removeDropdown()
        editor.model.change(writer => {
          const pos = editor.model.document.selection.getFirstPosition()
          writer.insertText(col, {}, pos)
        })
        editor.editing.view.focus()
      })
      dropdown.appendChild(item)
    })

    document.body.appendChild(dropdown)
    setTimeout(() => document.addEventListener('mousedown', removeDropdown, { once: true }), 0)
  }

  const showObjectsDropdown = () => {
    removeDropdown()
    const domSelection = window.getSelection()
    if (!domSelection.rangeCount) return
    const rect = domSelection.getRangeAt(0).getBoundingClientRect()

    dropdown = document.createElement('div')
    dropdown.style.cssText = `
      position: fixed; top: ${rect.bottom + 6}px; left: ${rect.left}px;
      background: white; border: 1px solid #ccc; border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999;
      min-width: 260px; max-height: 300px; overflow-y: auto;
    `
    const header = document.createElement('div')
    header.textContent = '📦 Tbl_Params 목록'
    header.style.cssText = `padding: 8px 12px; font-size: 12px; font-weight: bold; color: #555;
      background: #f7f7f7; border-bottom: 1px solid #eee; position: sticky; top: 0;`
    dropdown.appendChild(header)

    const tbl_params = tbl_params_ref.current || []
    if (tbl_params.length === 0) {
      const empty = document.createElement('div')
      empty.textContent = 'tbl_params 데이터가 없습니다.'
      empty.style.cssText = 'padding: 12px; font-size: 13px; color: #aaa;'
      dropdown.appendChild(empty)
    } else {
      tbl_params.forEach(obj => {
        const nm = obj.paramnm ?? ''
        const columns = obj.columns ?? ''
        const item = document.createElement('div')
        item.style.cssText = `padding: 8px 14px; cursor: pointer; font-size: 13px;
          display: flex; justify-content: space-between; align-items: center;
          border-bottom: 1px solid #f0f0f0; transition: background 0.1s;`
        const nameSpan = document.createElement('span')
        nameSpan.textContent = nm
        const typeSpan = document.createElement('span')
        typeSpan.textContent = Array.isArray(columns) ? columns.join(', ') : (columns || '')
        typeSpan.style.cssText = 'font-size: 10px; color: #999; background: #eee; border-radius: 3px; padding: 1px 5px;'
        item.appendChild(nameSpan)
        item.appendChild(typeSpan)
        item.addEventListener('mouseenter', () => (item.style.background = '#f0f7ff'))
        item.addEventListener('mouseleave', () => (item.style.background = ''))
        item.addEventListener('mousedown', (e) => {
          e.preventDefault()
          removeDropdown()
          editor.model.change(writer => {
            const pos = editor.model.document.selection.getFirstPosition()
            writer.insertText(`@${nm}`, { fontBackgroundColor: 'hsl(25, 90%, 85%)' }, pos)
          })
          editor.editing.view.focus()
        })
        dropdown.appendChild(item)
      })
    }

    document.body.appendChild(dropdown)
    setTimeout(() => document.addEventListener('mousedown', removeDropdown, { once: true }), 0)
  }

  const createSectionHeader = (title) => {
    const header = document.createElement('div')
    header.textContent = title
    header.style.cssText = `padding: 6px 12px; font-size: 11px; font-weight: bold;
      color: #fff; background: #5c8a5c; position: sticky; top: 0;`
    return header
  }

  const createItem = (label, onClickFn) => {
    const item = document.createElement('div')
    item.textContent = label
    item.style.cssText = `padding: 8px 14px; cursor: pointer; font-size: 13px;
      border-bottom: 1px solid #f0f0f0; transition: background 0.1s;`
    item.addEventListener('mouseenter', () => (item.style.background = '#f0f7ff'))
    item.addEventListener('mouseleave', () => (item.style.background = ''))
    item.addEventListener('mousedown', (e) => {
      e.preventDefault()
      removeDropdown()
      onClickFn()
      editor.editing.view.focus()
    })
    return item
  }

  const showIfDropdown = () => {
    removeDropdown()
    const domSelection = window.getSelection()
    if (!domSelection.rangeCount) return
    const rect = domSelection.getRangeAt(0).getBoundingClientRect()

    dropdown = document.createElement('div')
    dropdown.style.cssText = `
      position: fixed; top: ${rect.bottom + 6}px; left: ${rect.left}px;
      background: white; border: 1px solid #ccc; border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999;
      min-width: 260px; max-height: 350px; overflow-y: auto;
    `
    const tbl_params = tbl_params_ref.current || []
    const sca_params = sca_params_ref.current || []

    if (tbl_params.length > 0) {
      dropdown.appendChild(createSectionHeader('📦 TBL Params'))
      tbl_params.forEach(obj => {
        const nm = obj.paramnm ?? ''
        dropdown.appendChild(createItem(nm, () => {
          editor.model.change(writer => {
            const pos = editor.model.document.selection.getFirstPosition()
            writer.insertText(`@${nm}`, { fontBackgroundColor: 'hsl(25, 90%, 85%)' }, pos)
          })
        }))
      })
    }

    if (sca_params.length > 0) {
      dropdown.appendChild(createSectionHeader('🔍 SCA Params'))
      sca_params.forEach(obj => {
        const nm = obj.paramnm ?? ''
        dropdown.appendChild(createItem(nm, () => {
          editor.model.change(writer => {
            const pos = editor.model.document.selection.getFirstPosition()
            writer.insertText(`@${nm}`, { fontBackgroundColor: 'hsl(25, 90%, 85%)' }, pos)
          })
        }))
      })
    }

    if (tbl_params.length === 0 && sca_params.length === 0) {
      const empty = document.createElement('div')
      empty.textContent = '데이터가 없습니다.'
      empty.style.cssText = 'padding: 12px; font-size: 13px; color: #aaa;'
      dropdown.appendChild(empty)
    }

    document.body.appendChild(dropdown)
    setTimeout(() => document.addEventListener('mousedown', removeDropdown, { once: true }), 0)
  }

  const showScaDropdown = () => {
    removeDropdown()
    const domSelection = window.getSelection()
    if (!domSelection.rangeCount) return
    const rect = domSelection.getRangeAt(0).getBoundingClientRect()

    dropdown = document.createElement('div')
    dropdown.style.cssText = `
      position: fixed; top: ${rect.bottom + 6}px; left: ${rect.left}px;
      background: white; border: 1px solid #ccc; border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999;
      min-width: 260px; max-height: 300px; overflow-y: auto;
    `
    const header = document.createElement('div')
    header.textContent = '🔍 SCA Params 목록'
    header.style.cssText = `padding: 8px 12px; font-size: 12px; font-weight: bold; color: #555;
      background: #f7f7f7; border-bottom: 1px solid #eee; position: sticky; top: 0;`
    dropdown.appendChild(header)

    const sca_params = sca_params_ref.current || []
    if (sca_params.length === 0) {
      const empty = document.createElement('div')
      empty.textContent = 'sca_params 데이터가 없습니다.'
      empty.style.cssText = 'padding: 12px; font-size: 13px; color: #aaa;'
      dropdown.appendChild(empty)
    } else {
      sca_params.forEach(obj => {
        const nm = obj.paramnm ?? ''
        const item = document.createElement('div')
        item.textContent = nm
        item.style.cssText = `padding: 8px 14px; cursor: pointer; font-size: 13px;
          border-bottom: 1px solid #f0f0f0; transition: background 0.1s;`
        item.addEventListener('mouseenter', () => (item.style.background = '#f0f7ff'))
        item.addEventListener('mouseleave', () => (item.style.background = ''))
        item.addEventListener('mousedown', (e) => {
          e.preventDefault()
          removeDropdown()
          editor.model.change(writer => {
            const pos = editor.model.document.selection.getFirstPosition()
            const startPos = writer.createPositionAt(pos.parent, Math.max(0, pos.offset - 3))
            writer.remove(writer.createRange(startPos, pos))
            const newPos = editor.model.document.selection.getFirstPosition()
            writer.insertText(`{{@${nm}}}`, { fontBackgroundColor: 'hsl(120, 60%, 80%)' }, newPos)
          })
          editor.editing.view.focus()
        })
        dropdown.appendChild(item)
      })
    }

    document.body.appendChild(dropdown)
    setTimeout(() => document.addEventListener('mousedown', removeDropdown, { once: true }), 0)
  }

  const showScaColumnsDropdown = (columns, paramnm) => {
    removeDropdown()
    const domSelection = window.getSelection()
    if (!domSelection.rangeCount) return
    const rect = domSelection.getRangeAt(0).getBoundingClientRect()

    dropdown = document.createElement('div')
    dropdown.style.cssText = `
      position: fixed; top: ${rect.bottom + 6}px; left: ${rect.left}px;
      background: white; border: 1px solid #ccc; border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999;
      min-width: 200px; max-height: 250px; overflow-y: auto;
    `
    const header = document.createElement('div')
    header.textContent = `📋 ${paramnm} 컬럼 선택`
    header.style.cssText = `padding: 8px 12px; font-size: 12px; font-weight: bold; color: #555;
      background: #f7f7f7; border-bottom: 1px solid #eee; position: sticky; top: 0;`
    dropdown.appendChild(header)

    columns.forEach(col => {
      const item = document.createElement('div')
      item.textContent = col
      item.style.cssText = `padding: 8px 14px; cursor: pointer; font-size: 13px;
        border-bottom: 1px solid #f0f0f0; transition: background 0.1s;`
      item.addEventListener('mouseenter', () => (item.style.background = '#f0f7ff'))
      item.addEventListener('mouseleave', () => (item.style.background = ''))
      item.addEventListener('mousedown', (e) => {
        e.preventDefault()
        removeDropdown()
        editor.model.change(writer => {
          const pos = editor.model.document.selection.getFirstPosition()

          // ✅ 현재 줄 전체 텍스트 추출
          let fullLineText = ''
          for (const node of pos.parent.getChildren()) {
            if (node.is('$text')) fullLineText += node.data
          }
          const textBeforeCursor = fullLineText.slice(0, pos.offset)

          // ✅ 커서 뒤 텍스트 확인
          const textAfterCursor = fullLineText.slice(pos.offset)

          // ✅ 컨텍스트에 따라 색상 결정
          // {{#if @... → if 구문 색상
          // {{@...     → 단일행 변수 색상
          let bgColor
          if (textBeforeCursor.includes('{{#if')) {
            bgColor = 'hsl(25, 90%, 85%)'   // if 구문 색
          } else if (textBeforeCursor.includes('{{@')) {
            bgColor = 'hsl(120, 60%, 80%)'  // 단일행 변수 색
          } else {
            bgColor = 'hsl(120, 60%, 80%)'  // 기본값
          }

          // ✅ 수정 코드
          // 괄호 안에 있으면 (unclosed '(' 존재) }} 추가 안 함
          const openParenCount  = (textBeforeCursor.match(/\(/g) || []).length
          const closeParenCount = (textBeforeCursor.match(/\)/g) || []).length
          const isInsideParen   = openParenCount > closeParenCount

          const insertText = (textAfterCursor.startsWith('}}') || isInsideParen)
            ? col
            : `${col}}}`
          writer.insertText(insertText, { fontBackgroundColor: bgColor }, pos)
        })
        editor.editing.view.focus()
      })
      dropdown.appendChild(item)
    })

    document.body.appendChild(dropdown)
    setTimeout(() => document.addEventListener('mousedown', removeDropdown, { once: true }), 0)
  }

  const showDropdown = (options, keyword) => {
    removeDropdown()
    const domSelection = window.getSelection()
    if (!domSelection.rangeCount) return
    const rect = domSelection.getRangeAt(0).getBoundingClientRect()

    dropdown = document.createElement('div')
    dropdown.style.cssText = `
      position: fixed; top: ${rect.bottom + 6}px; left: ${rect.left}px;
      background: white; border: 1px solid #ccc; border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 9999; min-width: 220px; overflow: hidden;
    `
    const header = document.createElement('div')
    header.textContent = `"${keyword}" 구문 선택`
    header.style.cssText = `padding: 6px 12px; font-size: 11px; color: #888; background: #f7f7f7; border-bottom: 1px solid #eee;`
    dropdown.appendChild(header)

    options.forEach(opt => {
      const item = document.createElement('div')
      item.textContent = opt.label
      item.style.cssText = `padding: 9px 14px; cursor: pointer; font-size: 13px; transition: background 0.1s;`
      item.addEventListener('mouseenter', () => (item.style.background = '#f0f7ff'))
      item.addEventListener('mouseleave', () => (item.style.background = ''))
      item.addEventListener('mousedown', (e) => {
        e.preventDefault()
        removeDropdown()
        editor.model.change(writer => {
          const pos = editor.model.document.selection.getFirstPosition()
          const deleteLen = keyword.length + 1
          const startPos = writer.createPositionAt(pos.parent, Math.max(0, pos.offset - deleteLen))
          writer.remove(writer.createRange(startPos, pos))
          const newPos = editor.model.document.selection.getFirstPosition()
          const fragment = writer.createDocumentFragment()
          opt.lines.forEach(line => {
            const para = writer.createElement('paragraph')
            if (line.trim() === '') {
              writer.appendText(line, para)
            } else {
              writer.appendText(line, { fontColor: opt.color }, para)
            }
            writer.append(para, fragment)
          })
          editor.model.insertContent(fragment, newPos)
        })
        editor.editing.view.focus()
      })
      dropdown.appendChild(item)
    })

    document.body.appendChild(dropdown)
    setTimeout(() => document.addEventListener('mousedown', removeDropdown, { once: true }), 0)
  }

  editor.editing.view.document.on('keyup', (_evt, data) => {
    const keyCode = data.domEvent.keyCode
    const pos = editor.model.document.selection.getFirstPosition()
    if (!pos) return

    let fullText = ''
    for (const node of pos.parent.getChildren()) {
      if (node.is('$text')) fullText += node.data
    }
    const textBeforeCursor = fullText.slice(0, pos.offset)

    const regex = /\}\}\(([^}]+)\, /g

    if (textBeforeCursor.endsWith('{{@')) {
      showScaDropdown()
      return
    }

    // ✅ 여기에 추가! ──────────────────────────────
    const scaDotMatch = textBeforeCursor.match(/@([\w]+)\.$/)
    if (scaDotMatch) {
      const paramnm = scaDotMatch[1]
      const sca_params = sca_params_ref.current || []
      const found = sca_params.find(p => p.paramnm === paramnm)
      if (found) {
        showScaColumnsDropdown(found.columns, paramnm)
        return
      }
    }

    if (textBeforeCursor.endsWith('}}(') || textBeforeCursor.match(regex)) {
      const paramnm = findCurrentForParamnm()
      if (paramnm) {
        const tbl_params = tbl_params_ref.current || []
        const found = tbl_params.find(p => p.paramnm === paramnm)
        if (found) {
          let columns = found.columns
          if (typeof columns === 'string') {
            try { columns = JSON.parse(columns) }
            catch { columns = columns.replace(/[\[\]"]/g, '').split(',').map(c => c.trim()) }
          }
          showColumnsDropdown(columns)
          return
        }
      }
    }

    if (keyCode === 32) {
      for (const trigger of TRIGGERS) {
        if (
          textBeforeCursor.endsWith(trigger.keyword + ' ') ||
          textBeforeCursor.endsWith(trigger.keyword)
        ) {
          if (trigger.type === 'tbl_params') {
            showObjectsDropdown()
          } else if (trigger.type === 'if_params') {
            showIfDropdown()
          } else {
            showDropdown(trigger.options, trigger.keyword)
          }
          return
        }
      }
    }

    if (keyCode !== 27) removeDropdown()
  })

  editor.editing.view.document.on('keydown', (_evt, data) => {
    if (data.domEvent.keyCode === 27) removeDropdown()
  })
}

function VariableHighlightPlugin(editor) {
  const HIGHLIGHT_COLOR = 'hsl(200, 80%, 85%)'

  const charToBlockOffset = (textMap, charIndex) => {
    let cursor = 0
    for (const { blockOffset, length } of textMap) {
      if (charIndex <= cursor + length) return blockOffset + (charIndex - cursor)
      cursor += length
    }
    return null
  }

  const highlightBlock = (writer, model, block) => {
    const textMap = []
    let fullText = ''
    let blockOffset = 0

    for (const node of block.getChildren()) {
      if (node.is('$text')) {
        textMap.push({ blockOffset, length: node.data.length })
        fullText += node.data
        blockOffset += node.data.length
      } else {
        blockOffset++
      }
    }

    if (!fullText) return
    
    // ✅ 일반 변수: {{변수명}} - 기존 색상
    const regexNormal = /\{\{(?![#@])[^}]*\}\}(\([^)]*\))?/g
    let match
    while ((match = regexNormal.exec(fullText)) !== null) {
      const startOffset = charToBlockOffset(textMap, match.index)
      const endOffset = charToBlockOffset(textMap, match.index + match[0].length)
      if (startOffset === null || endOffset === null) continue
      const range = model.createRange(
        model.createPositionAt(block, startOffset),
        model.createPositionAt(block, endOffset),
      )
      writer.setAttribute('fontBackgroundColor', HIGHLIGHT_COLOR, range) // hsl(200, 80%, 85%)
    }

    // ✅ 단일행 변수: {{@변수명}} - 초록 색상 추가
    const regexSca = /\{\{@[^}]*\}\}/g
    while ((match = regexSca.exec(fullText)) !== null) {
      const startOffset = charToBlockOffset(textMap, match.index)
      const endOffset = charToBlockOffset(textMap, match.index + match[0].length)
      if (startOffset === null || endOffset === null) continue
      const range = model.createRange(
        model.createPositionAt(block, startOffset),
        model.createPositionAt(block, endOffset),
      )
      writer.setAttribute('fontBackgroundColor', 'hsl(120, 60%, 80%)', range)
    }
  }

  const highlightInElement = (writer, model, element) => {
    for (const child of element.getChildren()) {
      if (!child.is('element')) continue
      const hasText = [...child.getChildren()].some(n => n.is('$text'))
      if (hasText) highlightBlock(writer, model, child)
      else highlightInElement(writer, model, child)
    }
  }

  const applyHighlights = () => {
    const model = editor.model
    const changes = Array.from(model.document.differ.getChanges())
    const onlyOurChange = changes.length > 0 && changes.every(
      c => c.type === 'attribute' && c.attributeKey === 'fontBackgroundColor',
    )
    if (onlyOurChange) return

    model.enqueueChange({ isUndoable: false }, writer => {
      highlightInElement(writer, model, model.document.getRoot())
    })
  }

  editor.model.document.on('change:data', applyHighlights)
}

// ──────────────────────────────────────────────
// 템플릿 구문 유효성 검사
// ──────────────────────────────────────────────
function validateTemplateBlocks(editorInstance) {
  if (!editorInstance) return []
  const data = editorInstance.getData()
  const parser = new DOMParser()
  const doc = parser.parseFromString(data, 'text/html')
  const lines = [...doc.body.querySelectorAll('p, li, div, h1, h2, h3, h4')]
    .map(el => el.textContent.trim() ?? '')

  const errors = []
  const stack = []

  const PATTERNS = {
    FOR_OPEN:    /^\{\{#FOR\s+@[^\s}]+\}\}$/,
    FOR_END:     /^\{\{#END FOR\}\}$/,
    FOR_END_ERR: /\{?#END FOR\}?$|^\{#END FOR(?!\}\})/,
    IF_OPEN:     /^\{\{#if\s+@[^\s}][^}]*\}\}$/,
    IF_ELSE:     /^\{\{#ELSE\}\}$/,
    IF_END:      /^\{\{#END if\}\}$/,
    IF_ELSE_ERR: /^\{\{#{2,}ELSE\}\}$|^\{\{ELSE\}\}$|^\{#ELSE\}$/,
    IF_END_ERR:  /\{?#END if\}?$|^\{#END if(?!\}\})/,
  }

  lines.forEach((line, idx) => {
    const lineNo = idx + 1
    if (!line) return

    if (!PATTERNS.FOR_END.test(line) && PATTERNS.FOR_END_ERR.test(line)) {
      errors.push(`${lineNo}번째 줄: FOR 닫기 태그 오타 → "${line}"\n올바른 형식: {{#END FOR}}`); return
    }
    if (!PATTERNS.IF_END.test(line) && PATTERNS.IF_END_ERR.test(line)) {
      errors.push(`${lineNo}번째 줄: IF 닫기 태그 오타 → "${line}"\n올바른 형식: {{#END if}}`); return
    }
    if (!PATTERNS.IF_ELSE.test(line) && PATTERNS.IF_ELSE_ERR.test(line)) {
      errors.push(`${lineNo}번째 줄: ELSE 태그 오타 → "${line}"\n올바른 형식: {{#ELSE}}`); return
    }

    if (PATTERNS.FOR_OPEN.test(line))       stack.push({ type: 'FOR', line: lineNo })
    else if (PATTERNS.IF_OPEN.test(line))   stack.push({ type: 'IF', line: lineNo, hasElse: false })
    else if (PATTERNS.IF_ELSE.test(line)) {
      const top = stack[stack.length - 1]
      if (!top || top.type !== 'IF') errors.push(`${lineNo}번째 줄: {{#ELSE}} 앞에 {{#if}}가 없습니다.`)
      else top.hasElse = true
    } else if (PATTERNS.FOR_END.test(line)) {
      const top = stack[stack.length - 1]
      if (!top || top.type !== 'FOR') errors.push(`${lineNo}번째 줄: {{#END FOR}} 앞에 {{#FOR}}가 없습니다.`)
      else stack.pop()
    } else if (PATTERNS.IF_END.test(line)) {
      const top = stack[stack.length - 1]
      if (!top || top.type !== 'IF') errors.push(`${lineNo}번째 줄: {{#END if}} 앞에 {{#if}}가 없습니다.`)
      else stack.pop()
    }
  })

  stack.forEach(u => errors.push(`${u.line}번째 줄에서 시작한 {{#${u.type}}} 블록이 닫히지 않았습니다.`))
  return errors
}

// ──────────────────────────────────────────────
// 에디터 내용 파싱 → formats 배열 반환
// ──────────────────────────────────────────────
function parseEditorFormats(editorInstance, existingFormats, tbl_params, sca_params) {
  if (!editorInstance) return []
  const data = editorInstance.getData()
  const parser = new DOMParser()
  const doc = parser.parseFromString(data, 'text/html')
  const lines = [...doc.body.querySelectorAll('p, li, div, h1, h2, h3, h4')]
    .map(el => el.textContent.trim() ?? '')

  const newFormats = []
  const seenNames = new Set()

  // ✅ forStack → blockStack 으로 통합 (FOR / IF 모두 추적)
  const blockStack = [] // { type: 'FOR' | 'IF', paramnm: string }

  const cleanPatternName = (raw) =>
    raw?.replace(/<[^>]*>/g, '').replace(/&nbsp;/gi, '').trim()

  for (const line of lines) {
    if (!line) continue

    // ✅ FOR 시작
    const forStart = line.match(/^\{\{#FOR\s+@([^\s}]+)\}\}$/)
    if (forStart) {
      blockStack.push({ type: 'FOR', paramnm: forStart[1] })
      continue
    }

    // ✅ FOR 종료
    if (/^\{\{#END FOR\}\}$/.test(line)) {
      const idx = [...blockStack].reverse().findIndex(b => b.type === 'FOR')
      if (idx !== -1) blockStack.splice(blockStack.length - 1 - idx, 1)
      continue
    }

    // ✅ IF 시작
    const ifStart = line.match(/^\{\{#if\s+@([^\s}]+)[^}]*\}\}$/)
    if (ifStart) {
      blockStack.push({ type: 'IF', paramnm: ifStart[1] })
      continue
    }

    // ✅ IF 종료
    if (/^\{\{#END if\}\}$/.test(line)) {
      const idx = [...blockStack].reverse().findIndex(b => b.type === 'IF')
      if (idx !== -1) blockStack.splice(blockStack.length - 1 - idx, 1)
      continue
    }

    // ELSE 는 스택 변경 없음
    if (/^\{\{#ELSE\}\}$/.test(line)) continue

    // ✅ 현재 가장 안쪽 블록 판단
    const currentBlock   = blockStack.length > 0 ? blockStack[blockStack.length - 1] : null
    const currentForArray = currentBlock?.type === 'FOR' ? currentBlock.paramnm : null
    const functionnm      = currentBlock?.type ?? null  // 'FOR' | 'IF' | null
    const datauid = currentForArray
      ? (tbl_params.find(p => p.paramnm === currentForArray)?.datauid ?? null)
      : null

    // 함수형: {{이름}}(col1, col2)
    const funcMatch = line.match(/\{\{([^}]+)\}\}\(([^)]*)\)/)
    if (funcMatch) {
      const nm = cleanPatternName(funcMatch[1])
      const params = funcMatch[2].split(',').map(p => p.trim()).filter(Boolean)
      const params_org = funcMatch[2]
      if (nm && !nm.startsWith('#') && !nm.startsWith('@') && !seenNames.has(nm)) {
        seenNames.add(nm)
        const existing = existingFormats.find(f => f.objectNm === nm)

        // ✅ FOR 블록 기준 datauid
        let resolvedDatauid = datauid

        // ✅ datauid 없으면 params 안의 @paramnm.col 에서 추출
        if (!resolvedDatauid) {
          for (const param of params) {
            // @Deviation.deviation_nm 형태 파싱
            const paramMatch = param.trim().match(/^@([\w]+)\./)
            if (paramMatch) {
              const paramnm = paramMatch[1]
              // sca_params 에서 먼저 찾고
              const foundSca = sca_params.find(p => p.paramnm === paramnm)
              if (foundSca?.datauid) { resolvedDatauid = foundSca.datauid; break }
              // tbl_params 에서도 찾기
              const foundTbl = tbl_params.find(p => p.paramnm === paramnm)
              if (foundTbl?.datauid) { resolvedDatauid = foundTbl.datauid; break }
            }
          }
        }

        newFormats.push({
          objectUID:    existing?.objectUID ?? null,
          objectNm:     nm,
          chapterUID:   existing?.chapterUID ?? null,
          objectTypeCd: existing?.objectTypeCd ?? null,
          filters: {
            for_array:  currentForArray,
            params,
            datauid:    resolvedDatauid,  // ✅ FOR 기준 or params 기준
            params_org,
            functionnm,
          },
        })
      }
      continue
    }

    // 일반형: {{이름}}
    for (const m of [...line.matchAll(/\{\{([^}]+)\}\}/g)]) {
      const nm = cleanPatternName(m[1])
      if (!nm || nm.startsWith('#') || nm.startsWith('@') || seenNames.has(nm)) continue
      seenNames.add(nm)
      const existing = existingFormats.find(f => f.objectNm === nm)
      const scadatauid = sca_params.find(p => p.paramnm === nm)?.datauid ?? null
      newFormats.push({
        objectUID:    existing?.objectUID ?? null,
        objectNm:     nm,
        chapterUID:   existing?.chapterUID ?? null,
        objectTypeCd: existing?.objectTypeCd ?? null,
        filters: {
          for_array:   currentForArray,
          params:      [],
          docvariableuid: datauid ?? scadatauid,
          functionnm,  // ✅ 'FOR' | 'IF' | null
        },
      })
    }
  }
  return newFormats
}

// ══════════════════════════════════════════════
// 메인 컴포넌트
// ══════════════════════════════════════════════
export default function MasterChapterTemplatePage() {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const chapteruid = searchParams.get('chapteruid')
  const docid = searchParams.get('docid')
  const qc = useQueryClient()

  // ── 상태 ──
  const [formats, setFormats] = useState([])
  const [saveLoading, setSaveLoading] = useState(false)
  const [readLoading, setReadLoading] = useState(false)
  const initialized = useRef(false)
  const [filterModalFmt, setFilterModalFmt] = useState(null)
  const [filterInfo, setFilterInfo] = useState(null)
  const [filterModalLoading, setFilterModalLoading] = useState(false)
  const [filterSelectedDatauid, setFilterSelectedDatauid] = useState(null)
  const [filterColMappings, setFilterColMappings] = useState({})

  // ── 에디터 DOM refs ──
  const toolbarHostRef = useRef(null)
  const editorContainerRef = useRef(null)
  const editorInstanceRef = useRef(null)
  const isEditorReadyRef = useRef(false)
  const [containerMounted, setContainerMounted] = useState(false)
  const editorContainerCallbackRef = useCallback((node) => {
    editorContainerRef.current = node
    if (node) setContainerMounted(true)
  }, [])

  // AutoCompletePlugin 에서 항상 최신 params 를 읽을 수 있도록 ref 사용
  const tbl_params_ref = useRef([])
  const sca_params_ref = useRef([])

  // ── API ──
  const { data, isLoading } = useQuery({
    queryKey: ['chapter-template', chapteruid],
    queryFn: () => apiClient.get(`/chapters/${chapteruid}/template`).then(r => r.data),
    enabled: !!chapteruid,
  })

  const { data: chaptersData } = useQuery({
    queryKey: ['chapters', docid],
    queryFn: () => apiClient.get('/chapters', { params: { docid: Number(docid) } }).then(r => r.data),
    enabled: !!docid,
  })
  const chaptersList = chaptersData?.chapters || []

  const chapter    = data?.chapter    || {}
  const tbl_params = data?.tbl_params || []
  const sca_params = data?.sca_params || []
  const editYn     = chapter.editbuttonyn === 'Y'

  // ── 문서 데이터셋 (필터 모달용) ──
  const { data: docParamsData } = useQuery({
    queryKey: ['doc-params', docid],
    queryFn: () => apiClient.get(`/docs/${docid}/doc-params`).then(r => r.data),
    enabled: !!docid,
  })
  const docSelectedDatauids = docParamsData?.selected_datauids || []
  const docDatas = (docParamsData?.datas || []).filter(d => docSelectedDatauids.includes(d.datauid))
  const docColMap = docParamsData?.col_map || {}

  // params ref 동기화
  useEffect(() => { tbl_params_ref.current = tbl_params }, [tbl_params])
  useEffect(() => { sca_params_ref.current = sca_params }, [sca_params])

  useEffect(() => {
    initialized.current = false
    setFormats([])
  }, [chapteruid])

  // ── formats 초기화 (데이터 로드 후 1회) + isFilterMapped 최신값 반영 ──
  useEffect(() => {
    if (!data) return
    const objects = data.objects || []
    if (!initialized.current) {
      setFormats(
        objects
          .map(o => ({
            objectUID:      o.objectuid,
            objectNm:       o.objectnm?.trim() ?? '',
            objectTypeCd:   o.objecttypecd?.trim() ?? '',
            chapterUID:     o.chapteruid?.trim() ?? '',
            orderno:        o.orderno ?? 0,
            isFilter:       o.is_filter ?? false,
            isFilterMapped: o.is_filtermapped ?? false,
          }))
          .sort((a, b) => (b.orderno ?? 0) - (a.orderno ?? 0)),
      )
      initialized.current = true
      return
    }
    // 초기화 후 재fetch 시 isFilterMapped 최신값만 반영 (사용자 편집 내용 유지)
    setFormats(prev => prev.map(fmt => {
      const s = objects.find(o => o.objectuid === fmt.objectUID)
      if (!s) return fmt
      return { ...fmt, isFilter: s.is_filter ?? false, isFilterMapped: s.is_filtermapped ?? false }
    }))
  }, [data])

  // ── CKEditor 초기화 ──
  useEffect(() => {
    if (!data || !containerMounted || editorInstanceRef.current) return
    if (!window.DecoupledEditor) {
      console.error('window.DecoupledEditor 가 없습니다. ckeditor.js 로딩 확인 필요.')
      return
    }

    let cancelled = false

    // ✅ 핵심 수정:
    // 화살표 함수 `(editor) => AutoCompletePlugin(...)` 은 new 로 호출할 수 없어
    // "TypeError: e is not a constructor" 에러를 발생시킵니다.
    // CKEditor는 extraPlugins 항목을 내부적으로 `new Plugin(editor)` 형태로 호출하므로
    // 반드시 일반 함수(function declaration/expression)여야 합니다.
    function AutoCompletePluginWrapper(editor) {
      AutoCompletePlugin(editor, tbl_params_ref, sca_params_ref)
    }

    window.DecoupledEditor.create(editorContainerRef.current, {
      extraPlugins: [
        VariablePlugin,
        TemplateBlockPlugin,
        AutoCompletePluginWrapper,   // ✅ 화살표 함수 → 일반 함수로 교체
        VariableHighlightPlugin,
      ],
      htmlSupport: {
        allow: [{ name: /.*/, attributes: true, classes: true, styles: true }],
      },
      htmlEmbed: { showPreviews: true },
      toolbar: {
        items: [
          'insertIfElse', 'insertFor', '|',
          'pageBreak', '|',
          'fontSize', '|',
          'bold', 'italic', 'underline', 'strikethrough', '|',
          'fontColor', 'fontBackgroundColor', '|',
          'nativeColorPicker', 'nativeColorPicker_back', '|',
          'alignment', '|',
          'outdent', 'indent', '|',
          'insertTable', 'blockQuote', '|',
          'undo', 'redo', '|',
        ],
      },
      language: 'ko',
      table: { contentToolbar: ['tableColumn', 'tableRow', 'mergeTableCells'] },
      heading: {
        options: [
          { model: 'paragraph', title: '본문',   class: 'ck-heading_paragraph' },
          { model: 'heading1',  view: 'h1', title: '제목 1', class: 'ck-heading_heading1' },
          { model: 'heading2',  view: 'h2', title: '제목 2', class: 'ck-heading_heading2' },
          { model: 'heading3',  view: 'h3', title: '제목 3', class: 'ck-heading_heading3' },
          { model: 'heading4',  view: 'h4', title: '제목 4', class: 'ck-heading_heading4' },
        ],
      },
      fontSize: { options: [9, 10, 11, 13, 14, 16, 20, 24, 28], supportAllValues: true },
      fontFamily: {
        options: ['굴림체, GulimChe, sans-serif'],
        supportAllValues: true,
        default: '굴림체, GulimChe, sans-serif',
      },
      fontColor: {
        columns: 5,
        colorPicker: { format: 'hex' },
        documentColors: 10,
      },
      fontBackgroundColor: {
        columns: 5,
        colorPicker: { format: 'hex' },
        documentColors: 10,
      },
    }).then(editor => {
      if (cancelled) { editor.destroy(); return }

      if (toolbarHostRef.current) {
        toolbarHostRef.current.innerHTML = ''   // ← 이 한 줄 추가
        toolbarHostRef.current.appendChild(editor.ui.view.toolbar.element)
      }

      editorInstanceRef.current = editor
      isEditorReadyRef.current  = true

      editor.setData(data.chapter?.texttemplate || '<p>자유롭게 양식을 설정 하십시요.</p>')
    }).catch(e => console.error('CKEditor 초기화 실패:', e))

    return () => {
      cancelled = true
      if (editorInstanceRef.current) {
        editorInstanceRef.current.destroy()
        editorInstanceRef.current = null
        isEditorReadyRef.current  = false
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, containerMounted])

  // ── 항목 추출 ──
  const extractFormats = useCallback(() => {
    if (!isEditorReadyRef.current || !editorInstanceRef.current) {
      message.warning('에디터가 아직 로드되지 않았습니다.')
      return
    }
    const errors = validateTemplateBlocks(editorInstanceRef.current)
    if (errors.length > 0) {
      modal.error({ title: '⚠️ 템플릿 구문 오류', content: errors.join('\n\n'), width: 500 })
      return
    }
    setReadLoading(true)
    const parsed = parseEditorFormats(
      editorInstanceRef.current,
      formats,
      tbl_params_ref.current,
      sca_params_ref.current,
    )
    setFormats(parsed)
    setReadLoading(false)
    message.success(`${parsed.length}개 항목을 추출했습니다.`)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formats, message, modal])

  // ── 커서에 텍스트 삽입 ──
  const insertAtCursor = useCallback((text, bgColor = null) => {
    if (!editorInstanceRef.current) return
    const editor = editorInstanceRef.current
    editor.model.change(writer => {
      const pos = editor.model.document.selection.getFirstPosition()
      if (!pos) return
      const attrs = bgColor ? { fontBackgroundColor: bgColor } : {}
      writer.insertText(text, attrs, pos)
    })
    editor.editing.view.focus()
  }, [])

  // ── 저장 뮤테이션 ──
  const saveMutation = useMutation({
    mutationFn: (body) => apiClient.post(`/chapters/${chapteruid}/template`, body).then(r => r.data),
    onSuccess: (res) => {
      setSaveLoading(false)
      if (res && res.ok === false) {
        message.error(`${res.message || '저장 실패'}${res.add ? '\n' + res.add : ''}`)
        return
      }
      message.success(`'${chapter.chapternm}' 저장되었습니다.`)
      initialized.current = false
      qc.invalidateQueries({ queryKey: ['chapter-template', chapteruid] })
    },
    onError: (err) => {
      setSaveLoading(false)
      message.error(err.response?.data?.detail || '저장 실패')
    },
  })

  const handleSave = useCallback(() => {
    if (!editYn) { message.warning('편집 권한이 없습니다.'); return }
    if (!isEditorReadyRef.current || !editorInstanceRef.current) {
      message.warning('에디터가 아직 로드되지 않았습니다.')
      return
    }

    const errors = validateTemplateBlocks(editorInstanceRef.current)
    if (errors.length > 0) {
      modal.error({ title: '⚠️ 템플릿 구문 오류', content: errors.join('\n\n'), width: 500 })
      return
    }

    const latestFormats = parseEditorFormats(
      editorInstanceRef.current,
      formats,
      tbl_params_ref.current,
      sca_params_ref.current,
    )
    setFormats(latestFormats)

    setSaveLoading(true)
    saveMutation.mutate({
      texttemplate: editorInstanceRef.current.getData(),
      formats: latestFormats,
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editYn, formats, message, modal, saveMutation])

  // ── 항목 편집 이동 ──
  const editToObjects = useCallback((fmt) => {
    const route = TYPE_ROUTE[fmt.objectTypeCd]
    if (!route) { message.warning('설정된 항목 타입이 없습니다.'); return }
    const enc = encodeURIComponent(fmt.objectNm)
    sessionStorage.setItem('chapter_template_chapteruid', chapteruid)
    navigate(`${route}?chapteruid=${chapteruid}&objectnm=${enc}`)
  }, [chapteruid, message, navigate])

  // ── 항목 설정 이동 ──
  const moveToObjects = useCallback((fmt) => {
    sessionStorage.setItem('chapter_template_chapteruid', chapteruid)
    if (fmt?.objectUID) {
      navigate(`/master/object?chapteruid=${chapteruid}&objectuid=${fmt.objectUID}`)
    } else {
      navigate(`/master/object?chapteruid=${chapteruid}`)
    }
  }, [chapteruid, navigate])

  // ── 필터 매핑 모달 오픈 ──
  const openFilterModal = useCallback(async (fmt) => {
    setFilterModalFmt(fmt)
    setFilterInfo(null)
    setFilterSelectedDatauid(null)
    setFilterColMappings({})
    setFilterModalLoading(true)
    try {
      const res = await apiClient.get(`/chapters/objectfilter/${fmt.objectUID}`).then(r => r.data)
      setFilterInfo(res)
      // 기존 매핑 복원 (다중 rows)
      if (res.maps && res.maps.length > 0) {
        setFilterSelectedDatauid(res.maps[0].objectdatauid)
        const initMappings = {}
        res.maps.forEach(row => {
          if (row.dfvcolnm && row.objectdatacolnm) initMappings[row.dfvcolnm] = row.objectdatacolnm
        })
        setFilterColMappings(initMappings)
      }
    } finally {
      setFilterModalLoading(false)
    }
  }, [])

  // ── 필터 매핑 저장 ──
  const saveFilterMap = useCallback(async () => {
    const dfvcolnms = filterInfo?.dfvcolnms || []
    if (!filterInfo?.filter || !filterSelectedDatauid) {
      message.warning('데이터셋을 선택해 주세요.')
      return
    }
    const unmapped = dfvcolnms.filter(col => !filterColMappings[col])
    if (unmapped.length > 0) {
      message.warning(`'${unmapped.join(', ')}' 컬럼을 매핑해 주세요.`)
      return
    }
    try {
      await apiClient.post('/chapters/objectfiltermap', {
        objectfilteruid: filterInfo.filter.objectfilteruid,
        dfvdatauid: filterInfo.filter.dfvdatauid,
        objectdatauid: filterSelectedDatauid,
        mappings: dfvcolnms.map(col => ({ dfvcolnm: col, objectdatacolnm: filterColMappings[col] })),
      })
      setFormats(prev => prev.map(f =>
        f.objectUID === filterModalFmt?.objectUID ? { ...f, isFilterMapped: true } : f
      ))
      message.success('필터 매핑이 저장되었습니다.')
      setFilterModalFmt(null)
    } catch {
      message.error('저장에 실패했습니다.')
    }
  }, [filterInfo, filterSelectedDatauid, filterColMappings, filterModalFmt, message])

  if (!chapteruid) return <div style={{ padding: 24, color: '#888' }}>chapteruid가 없습니다.</div>

  return (
    <div style={{ height: '100%' }}>
      {/* 페이지 헤더 */}
      <div style={{ marginBottom: 12 }}>
        {/* 최상단: 타이틀 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div style={{ width: 4, height: 22, background: 'linear-gradient(#1677ff,#69b1ff)', borderRadius: 2 }} />
          <span style={{ fontSize: 16, fontWeight: 700 }}>챕터 템플릿 관리</span>
        </div>
        {/* 상단: 챕터 선택(좌) / 버튼(우) */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, color: '#555' }}>챕터</span>
            <Select
              value={chapteruid}
              onChange={(uid) => navigate(`/master/chapter-template?chapteruid=${uid}&docid=${docid || ''}`)}
              style={{ width: 200 }}
              size="small"
              options={chaptersList.map(c => ({ value: c.chapteruid, label: c.chapternm }))}
            />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={extractFormats}
              disabled={readLoading}
              style={{
                padding: '5px 14px', border: 'none', borderRadius: 4, cursor: readLoading ? 'wait' : 'pointer',
                background: '#D1D1D1', color: '#000', fontSize: 13, fontWeight: 500,
              }}
            >항목 추출</button>
            <button
              onClick={handleSave}
              disabled={saveLoading}
              style={{
                padding: '5px 14px', border: 'none', borderRadius: 4, cursor: saveLoading ? 'wait' : 'pointer',
                background: '#2B9CFF', color: '#fff', fontSize: 13, fontWeight: 500,
              }}
            >저장</button>
          </div>
        </div>
      </div>

      {/* 에디터 레이아웃 — 항상 렌더링 (로딩 중에도 div를 DOM에 유지해야 CKEditor ref가 유효) */}
      <div style={{ display: 'flex', gap: 20, height: 'calc(100% - 48px)', position: 'relative' }}>

        {/* 로딩 오버레이 */}
        {isLoading && (
          <div style={{
            position: 'absolute', inset: 0, background: 'rgba(255,255,255,0.8)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10,
          }}>
            <Spin />
          </div>
        )}

        {/* ─── 좌측: 에디터 ─── */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          {/* 툴바 호스트 — CKEditor가 여기에 toolbar element를 append */}
          <div ref={toolbarHostRef} />

          {/* CKEditor editable 래퍼 */}
          <div
            ref={editorContainerCallbackRef}
            spellCheck={false}
            style={{
              border: '2px solid #4CAF50',
              height: 600,
              overflowY: 'auto',
              backgroundColor: 'white',
              // flex: 1,
            }}
          />
        </div>

        {/* ─── 우측: 변수/서식 패널 ─── */}
        <div style={{ flex:0.4, minWidth: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>

          {/* 단일행 변수 + 테이블 변수 */}
          <div style={{ display: 'flex', gap: 12 }}>
            {/* 단일행 변수 */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{ fontSize: 12, margin: '9px 0' }}>🔍 단일행 변수</h2>
              {sca_params.length > 0 ? (
                <div style={{ height: 120, overflowY: 'auto' }}>
                  {sca_params.flatMap((p) =>
                    (p.columns || []).map((col) => {
                      const varName = `${p.paramnm}.${col}`
                      return (
                        <div
                          key={varName}
                          style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '6px 8px', border: '1px solid #ddd', borderRadius: 6,
                            marginTop: 5,
                          }}
                        >
                          <label style={{ fontSize: 12, wordBreak: 'break-all' }}>{varName}</label>
                          <button
                            className="var-insert-btn"
                            title="에디터에 삽입"
                            onMouseDown={(e) => {
                              e.preventDefault()
                              insertAtCursor(`{{@${varName}}}`, 'hsl(120, 60%, 80%)')
                            }}
                          >⚡</button>
                        </div>
                      )
                    })
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: '#777' }}>데이터 없음</div>
              )}
            </div>

            {/* 다중행 변수 */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2 style={{ fontSize: 12, margin: '9px 0' }}>📦 다중행 변수</h2>
              {tbl_params.length > 0 ? (
                <div style={{ height: 120, overflowY: 'auto' }}>
                  {tbl_params.map((p, i) => (
                    <div
                      key={p.paramnm}
                      style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '6px 8px', border: '1px solid #ddd', borderRadius: 6,
                        marginTop: 5, animation: `fadeIn 0.2s ease forwards`,
                        animationDelay: `${i * 0.02}s`, opacity: 0,
                      }}
                    >
                      <label style={{ fontSize: 12, wordBreak: 'break-all' }}>{p.paramnm}</label>
                      <button
                        className="var-insert-btn"
                        title="에디터에 삽입"
                        onMouseDown={(e) => { e.preventDefault(); insertAtCursor(`{{@${p.paramnm}}}`, 'hsl(25, 90%, 85%)') }}
                      >⚡</button>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: '#777' }}>데이터 없음</div>
              )}
            </div>
          </div>

          {/* 안내 박스 */}
          <div style={{
            backgroundColor: '#f9fbe7', borderRadius: 6, color: '#6a7d3c',
            padding: '6px 10px', fontSize: 12,
          }}>
            ＊반드시 저장 클릭 후 관리 페이지 이동 바랍니다.
          </div>

          {/* 항목 관리 */}
          <div>
            <h2 style={{ fontSize: 12, margin: '9px 0' }}>항목 관리</h2>


            {/* 항목 목록 */}
            {formats.length > 0 ? (
              <div style={{ height: 360, overflowY: 'auto' }}>
                {formats.map((fmt, i) => (
                  <div
                    key={fmt.objectUID || fmt.objectNm}
                    style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '6px 8px', border: '1px solid #ddd', borderRadius: 6,
                      marginTop: 5, animation: `fadeIn 0.2s ease forwards`,
                      animationDelay: `${i * 0.02}s`, opacity: 0,
                    }}
                  >
                    <label style={{ fontSize: 12, wordBreak: 'break-all' }}>{fmt.objectNm}</label>

                    {/* 우측: 설정아이콘 | Filter 뱃지 */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                      
                      {/* 설정 아이콘 */}
                      <button
                        className="icon-btn"
                        title="해당 변수 수정 이동"
                        disabled={!fmt.objectUID}
                        style={{ cursor: fmt.objectUID ? 'pointer' : 'not-allowed' }}
                        onClick={() => editToObjects(fmt)}
                      >
                        <img src="/icons/configuration.svg" className="icon-img" alt="항목 설정" />
                      </button>

                      {/* Filter 버튼 자리 (항상 고정 너비) */}
                      <div style={{ width: 38, display: 'flex', justifyContent: 'center' }}>
                        {fmt.isFilter && (
                          <button
                            onClick={() => openFilterModal(fmt)}
                            disabled={!fmt.objectUID}
                            style={{
                              fontSize: 9, fontWeight: 600, padding: '2px 6px',
                              borderRadius: 3, lineHeight: 1.6, border: 'none',
                              background: fmt.isFilterMapped ? '#1677ff' : '#bfbfbf',
                              color: '#fff',
                              cursor: fmt.objectUID ? 'pointer' : 'not-allowed',
                              width: '100%',
                            }}
                          >
                            Filter
                          </button>
                        )}
                      </div>

                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: '#777', fontSize: 14, lineHeight: 1.6 }}>
                에디터에 <code>{`{{명칭}}`}</code> 형태로 입력한 후<br />
                <strong>읽기</strong> 버튼을 클릭하세요
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 필터 매핑 모달 */}
      <Modal
        title="필터 매핑 설정"
        open={!!filterModalFmt}
        onCancel={() => setFilterModalFmt(null)}
        onOk={saveFilterMap}
        okText="저장"
        cancelText="취소"
        width={520}
      >
        {filterModalLoading ? (
          <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
        ) : filterInfo?.filter ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* 필터 변수 정보 */}
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>필터 변수</div>
              <div style={{ fontSize: 13 }}>
                {filterInfo.filter.dfvnm}
                {filterInfo.filter.dfvcolnms && (
                  <span style={{ color: '#888' }}> ({filterInfo.filter.dfvcolnms})</span>
                )}
              </div>
            </div>

            {/* 데이터셋 선택 (공통) */}
            <div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>매핑할 데이터셋</div>
              <Select
                style={{ width: '100%' }}
                placeholder="데이터셋 선택"
                value={filterSelectedDatauid}
                onChange={(v) => { setFilterSelectedDatauid(v); setFilterColMappings({}) }}
                options={docDatas.map(d => ({ value: d.datauid, label: d.datanm }))}
              />
            </div>

            {/* 필터 컬럼별 매핑 */}
            {filterSelectedDatauid && (filterInfo.dfvcolnms || []).length > 0 && (
              <div>
                <div style={{ fontSize: 12, color: '#888', marginBottom: 6 }}>컬럼 매핑</div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#fafafa' }}>
                      <th style={{ padding: '6px 8px', border: '1px solid #e8e8e8', fontSize: 12, textAlign: 'left' }}>필터 컬럼</th>
                      <th style={{ padding: '6px 8px', border: '1px solid #e8e8e8', fontSize: 12, textAlign: 'left' }}>데이터셋 컬럼</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(filterInfo.dfvcolnms || []).map(col => (
                      <tr key={col}>
                        <td style={{ padding: '6px 8px', border: '1px solid #e8e8e8', fontSize: 13 }}>{col}</td>
                        <td style={{ padding: '4px 8px', border: '1px solid #e8e8e8' }}>
                          <Select
                            style={{ width: '100%' }}
                            size="small"
                            placeholder="컬럼 선택"
                            value={filterColMappings[col] || null}
                            onChange={v => setFilterColMappings(prev => ({ ...prev, [col]: v }))}
                            options={(docColMap[filterSelectedDatauid] || []).map(c => ({
                              value: c.querycolnm,
                              label: c.dispcolnm ? `${c.dispcolnm} (${c.querycolnm})` : c.querycolnm,
                            }))}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div style={{ color: '#888' }}>필터 정보를 불러올 수 없습니다.</div>
        )}
      </Modal>

      {/* fadeIn 키프레임 주입 */}
      <style>{`
        @keyframes fadeIn { to { opacity: 1; } }
        .var-insert-btn {
          flex-shrink: 0; width: 20px; height: 20px; font-size: 14px; line-height: 1;
          padding: 0; border: 1px solid #aaa; border-radius: 4px;
          background-color: #f0f7ff; color: #3a7bd5; cursor: pointer; font-weight: bold;
        }
        .var-insert-btn:hover { background-color: #3a7bd5; color: white; }
      `}</style>
    </div>
  )
}