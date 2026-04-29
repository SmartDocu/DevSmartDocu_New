# 다국어 Term Key 목록

프로젝트 전체 수집 기준일: 2026-04-29  
총 239개 (category 4 기준: btn/lbl/thd/ttl/inf) + 차트 속성 37개 추가

> **PK 충돌 해소 규칙**: `termkey`가 PK이므로 동일 base key가 여러 group에 속하면  
> `{basekey}_{group}` suffix 부여 (예: `orderno_lbl`, `orderno_thd`)

---

## 1. cod. (10개)

| term_key |
|----------|
| cod.align_center |
| cod.align_left |
| cod.align_right |
| cod.datasourcecd_df |
| cod.is_multirow_n |
| cod.is_multirow_y |
| cod.datasourcecd_dfv |
| cod.keycoldatatypecd_C |
| cod.keycoldatatypecd_D |
| cod.keycoldatatypecd_I |
| cod.useyn_n |
| cod.useyn_y |

---

## 2. msg. (73개)

| term_key |
|----------|
| msg.chapter.required |
| msg.chapter.select.delete |
| msg.code.groupcd.required |
| msg.code.select.delete |
| msg.code.select.trans |
| msg.code.value.required |
| msg.col.empty |
| msg.col.save.created |
| msg.confirm.delete |
| msg.confirm.file.overwrite |
| msg.datanm.required |
| msg.db.required |
| msg.delete.error |
| msg.delete.success |
| msg.doc.loading |
| msg.doc.name.duplicate |
| msg.doc.no.permission |
| msg.doc.not.found |
| msg.doc.required |
| msg.doc.select |
| msg.doc.select.delete |
| msg.docselect.error |
| msg.docselect.required |
| msg.dataset.filter.readonly |
| msg.docselect.tabs.close |
| msg.email.required |
| msg.favorite.error |
| msg.load.error |
| msg.loading |
| msg.login.failed |
| msg.menu.required |
| msg.menu.select.delete |
| msg.menu.select.trans |
| msg.message.required |
| msg.message.select.delete |
| msg.message.select.trans |
| msg.no.change.history |
| msg.no.data |
| msg.password.minlength |
| msg.password.mismatch |
| msg.password.required |
| msg.preparing |
| msg.preview.error |
| msg.project.not.found |
| msg.prompt.required |
| msg.register.failed |
| msg.register.success |
| msg.register.tenant.required |
| msg.register.terms.required |
| msg.required.docid |
| msg.reset.sent |
| msg.sample.empty |
| msg.save.col.created |
| msg.save.col.warn |
| msg.save.error |
| msg.save.success |
| msg.select |
| msg.select.chapter |
| msg.select.data |
| msg.select.delete |
| msg.select.placeholder |
| msg.select.project |
| msg.server.error |
| msg.source.select |
| msg.tab.maxcount |
| msg.template.none |
| msg.term.required |
| msg.term.select.delete |
| msg.term.select.trans |
| msg.usernm.required |
| msg.ph.email |
| msg.ph.tenant.select |
| msg.placeholder.password.change |
| msg.placeholder.password.confirm |
| msg.sidebar.favorites |
| msg.sidebar.search |

---

## 3. mnu. (5개)

| term_key |
|----------|
| mnu.master_data.docs.base |
| mnu.system.translation.codes |
| mnu.system.translation.menus |
| mnu.system.translation.messages |
| mnu.system.translation.terms |

---

## 4. 기타 prefix (btn / lbl / thd / ttl / inf)

> suffix 규칙: 동일 base key가 여러 group에 존재하면 `_{group}` 추가  
> 예) `orderno` → `orderno_lbl` (lbl), `orderno_thd` (thd)

### btn. (18개)

| term_key |
|----------|
| btn.apply |
| btn.cancel |
| btn.delete |
| btn.login_btn |
| btn.logout |
| btn.new |
| btn.object.manage |
| btn.objectconfig |
| btn.ok |
| btn.preview_btn |
| btn.register_btn |
| btn.reset.password |
| btn.reset.send |
| btn.save |
| btn.savecols |
| btn.template.edit |
| btn.upgrade |
| btn.upload_btn |

### lbl. (81개)

| term_key |
|----------|
| lbl.agree.all |
| lbl.align |
| lbl.bgcolor |
| lbl.billing.model |
| lbl.bold |
| lbl.bordercolor |
| lbl.billing.multi |
| lbl.billing.single |
| lbl.chapternm |
| lbl.chapterno |
| lbl.codegroupcd_lbl |
| lbl.codevalue_lbl |
| lbl.connectnm_lbl |
| lbl.connecttype_lbl |
| lbl.datanm_lbl |
| lbl.dataset_lbl |
| lbl.dataset.unused |
| lbl.dataset.used |
| lbl.datasourcecd_lbl |
| lbl.datauid |
| lbl.default_message |
| lbl.default_name_lbl |
| lbl.default_text_lbl |
| lbl.description |
| lbl.dim.cols |
| lbl.doc |
| lbl.docnm |
| lbl.email |
| lbl.encaccessuserid |
| lbl.encdatabase |
| lbl.encendpoint |
| lbl.file |
| lbl.fontcolor |
| lbl.fontsize |
| lbl.iconnm_lbl |
| lbl.joindt |
| lbl.keycoldatatypecd |
| lbl.keycolnm |
| lbl.measure.cols |
| lbl.menucd_lbl |
| lbl.messagekey_lbl |
| lbl.messagetypecd_lbl |
| lbl.myrole |
| lbl.nmcolnm |
| lbl.not.agreed |
| lbl.note |
| lbl.objectdesc_lbl |
| lbl.objectnm_lbl |
| lbl.objecttypecd_lbl |
| lbl.operator_lbl |
| lbl.optional |
| lbl.ordercolnm |
| lbl.orderno_lbl |
| lbl.paramnm_lbl |
| lbl.password |
| lbl.password.confirm |
| lbl.plan |
| lbl.plan.free |
| lbl.plan.pro |
| lbl.project |
| lbl.projectnm_lbl |
| lbl.prompt |
| lbl.query |
| lbl.required |
| lbl.reset.email |
| lbl.rolecd_lbl |
| lbl.route_path |
| lbl.sample |
| lbl.samplevalue |
| lbl.sort |
| lbl.source.data |
| lbl.status |
| lbl.template.upload |
| lbl.tenant |
| lbl.tenantnm |
| lbl.termgroupcd_lbl |
| lbl.termkey_lbl |
| lbl.theme |
| lbl.upload_lbl |
| lbl.usernm |
| lbl.useyn_lbl |

### lbl.chart.prop.* — 차트 속성 필드 레이블 (37개)

> `chart_definitions.py`의 각 property `term_key` 값. `MasterChartsPage` 설정 패널에 표시됨.

| term_key | 한국어 기본값 |
|----------|--------------|
| lbl.chart.prop.title | 그래프 제목 |
| lbl.chart.prop.xField | X축 필드 |
| lbl.chart.prop.xLabel | X축 제목 |
| lbl.chart.prop.yField | Y축 필드 |
| lbl.chart.prop.yLabel | Y축 제목 |
| lbl.chart.prop.categoryField | 범주 |
| lbl.chart.prop.colorPalette | 색상 테마 |
| lbl.chart.prop.showDataLabels | 값 라벨 표시 |
| lbl.chart.prop.barWidth | 막대 너비 |
| lbl.chart.prop.barGap | 막대 간 간격 |
| lbl.chart.prop.legendPosition | 범례 위치 |
| lbl.chart.prop.showMarkers | 마커 노출 |
| lbl.chart.prop.lineStyle | 선 스타일 |
| lbl.chart.prop.lineWidth | 선 두께 |
| lbl.chart.prop.marker | 마커 모양 |
| lbl.chart.prop.markerSize | 마커 크기 |
| lbl.chart.prop.labelField | 범주 필드 |
| lbl.chart.prop.valueField | 값 필드 |
| lbl.chart.prop.valueFormat | 값 포맷 |
| lbl.chart.prop.cutout | 구멍 크기 (%) |
| lbl.chart.prop.sizeField | 원 크기 필드 |
| lbl.chart.prop.showGroupLabels | 그룹 라벨 표시 |
| lbl.chart.prop.bins | 빈 개수 |
| lbl.chart.prop.rwidth | 막대 폭 비율 |
| lbl.chart.prop.notch | 노치 노출 |
| lbl.chart.prop.showMeans | 평균값 노출 |
| lbl.chart.prop.showFliers | 이상치 노출 |
| lbl.chart.prop.widths | 박스 너비 |
| lbl.chart.prop.whis | 수염 범위 |
| lbl.chart.prop.hbar.xField | y축 필드 (horizontalBar 전용) |
| lbl.chart.prop.hbar.xLabel | y축 제목 (horizontalBar 전용) |
| lbl.chart.prop.hbar.yField | x축 필드 (horizontalBar 전용) |
| lbl.chart.prop.hbar.yLabel | x축 제목 (horizontalBar 전용) |
| lbl.chart.prop.box.categoryField | X축 필드 (box plot 전용) |
| lbl.chart.prop.box.valueField | Y축 필드 (box plot 전용) |
| lbl.chart.prop.pareto.labelField | X축 데이터 (pareto 전용) |
| lbl.chart.prop.pareto.yField | Y축 데이터 (pareto 전용) |

### cod.chart.* — 차트 select 옵션 레이블 (29개)

| term_key | 한국어 기본값 |
|----------|--------------|
| cod.chart.legendpos.best | 자동 |
| cod.chart.legendpos.upper_right | 오른쪽 위 |
| cod.chart.legendpos.upper_left | 왼쪽 위 |
| cod.chart.legendpos.lower_left | 왼쪽 아래 |
| cod.chart.legendpos.lower_right | 오른쪽 아래 |
| cod.chart.legendpos.right | 오른쪽 |
| cod.chart.legendpos.center_left | 중앙 왼쪽 |
| cod.chart.legendpos.center_right | 중앙 오른쪽 |
| cod.chart.legendpos.lower_center | 하단 중앙 |
| cod.chart.legendpos.upper_center | 상단 중앙 |
| cod.chart.legendpos.center | 중앙 |
| cod.chart.linestyle.solid | 실선 |
| cod.chart.linestyle.dotted | 점선 |
| cod.chart.linestyle.dashed | 대시선 |
| cod.chart.linestyle.dash_dot | 대시-점선 |
| cod.chart.marker.circle | 원 |
| cod.chart.marker.square | 사각형 |
| cod.chart.marker.triangle | 삼각형 |
| cod.chart.marker.diamond | 다이아몬드 |
| cod.chart.valueformat.value | 값 |
| cod.chart.valueformat.percent | 백분율 |
| cod.chart.valueformat.value_percent | 값 + 백분율 |

### thd. (42개)

| term_key |
|----------|
| thd.align_thd |
| thd.bgcolor_thd |
| thd.bold_thd |
| thd.codegroupcd_thd |
| thd.codevalue_thd |
| thd.colnm |
| thd.comma |
| thd.connectnm_thd |
| thd.connecttype_thd |
| thd.datanm_thd |
| thd.datasourcecd_thd |
| thd.datatypecd |
| thd.decimal |
| thd.default_name_thd |
| thd.default_text_thd |
| thd.dispcolnm |
| thd.fontcolor_thd |
| thd.fontsize_thd |
| thd.languagecd |
| thd.move |
| thd.languagenm |
| thd.measureyn |
| thd.menucd_thd |
| thd.messagekey_thd |
| thd.messagetypecd_thd |
| thd.objectdesc_thd |
| thd.objectnm_thd |
| thd.objectsettingyn |
| thd.objecttypecd_thd |
| thd.operator_thd |
| thd.orderno_thd |
| thd.paramnm_thd |
| thd.projectnm_thd |
| thd.querycolnm |
| thd.rolecd_thd |
| thd.termgroupcd_thd |
| thd.termkey_thd |
| thd.translated_desc |
| thd.translated_text |
| thd.useyn_thd |
| thd.width_px |

### ttl. (29개)

| term_key |
|----------|
| ttl.ai.chart.manage |
| ttl.ai.sentence.manage |
| ttl.ai.table.manage |
| ttl.chapter.list |
| ttl.chart.manage |
| ttl.col.info |
| ttl.condition |
| ttl.data.list |
| ttl.data.preview |
| ttl.datacols |
| ttl.dataset_ttl |
| ttl.dataset.mapping |
| ttl.detail |
| ttl.header.settings |
| ttl.sentence.manage |
| ttl.docselect |
| ttl.docselect.change |
| ttl.list |
| ttl.login_ttl |
| ttl.myinfo.personal |
| ttl.myinfo.projects |
| ttl.myinfo.tenant |
| ttl.myinfo.tenant.history |
| ttl.myinfo.terms |
| ttl.preview_ttl |
| ttl.register_ttl |
| ttl.table.manage |
| ttl.translations |
| ttl.value.settings |

### inf. (5개)

| term_key |
|----------|
| inf.gensentence.default |
| inf.iconnm_inf |
| inf.password.hidden |
| inf.preview.empty |
| inf.preview.rows |

---

## 요약

| prefix | 개수 |
|--------|------|
| cod.   | 12   |
| msg.   | 75   |
| mnu.   | 5    |
| btn.   | 18   |
| lbl.   | 81   |
| thd.   | 42   |
| ttl.   | 24   |
| inf.   | 5    |
| **합계** | **267** |
