# 다국어 Term Key 목록

프로젝트 전체 수집 기준일: 2026-05-06  
ui_terms 테이블 기준 (DB 조회 결과로 업데이트)

> **참고**: `cod.chart.*` 옵션 키가 `lbl.chart.*` 로 prefix 변경됨 (DB 기준)

---

## 1. cod. (32개)

### code.align (3개)

| term_key | default_text |
|----------|--------------|
| cod.align_center | Center |
| cod.align_left | Left |
| cod.align_right | Right |

### code.datasourcecd (2개)

| term_key | default_text |
|----------|--------------|
| cod.datasourcecd_df | Dataset |
| cod.datasourcecd_dfv | Variable Dataset |

### code.is_multirow (2개)

| term_key | default_text |
|----------|--------------|
| cod.is_multirow_n | Single Row |
| cod.is_multirow_y | Multi Row |

### code.keycoldatatypecd (3개)

| term_key | default_text |
|----------|--------------|
| cod.keycoldatatypecd_C | Character |
| cod.keycoldatatypecd_D | Date |
| cod.keycoldatatypecd_I | Integer |

### code.menu_rolecd (5개)

| term_key | default_text |
|----------|--------------|
| cod.menu_rolecd_P | All User |
| cod.menu_rolecd_PM | Project Manager |
| cod.menu_rolecd_S | System User |
| cod.menu_rolecd_TM | Tenant Manager |
| cod.menu_rolecd_U | Login User |

### code.message_typecd (4개)

| term_key | default_text |
|----------|--------------|
| cod.message_typecd_confirm | confirm |
| cod.message_typecd_error | Error |
| cod.message_typecd_info | Information |
| cod.message_typecd_warn | warn |

### code.objecttypecd (6개)

| term_key | default_text |
|----------|--------------|
| cod.objecttypecd_CA | Chart |
| cod.objecttypecd_CU | Chart |
| cod.objecttypecd_SA | Sentence |
| cod.objecttypecd_SU | Sentence |
| cod.objecttypecd_TA | Table |
| cod.objecttypecd_TU | Table |

### code.term_groupcd (5개)

| term_key | default_text |
|----------|--------------|
| cod.term_groupcd_btn | Button |
| cod.term_groupcd_inf | Information |
| cod.term_groupcd_lbl | Label |
| cod.term_groupcd_thd | Table Header |
| cod.term_groupcd_ttl | Title |

### code.useyn (2개)

| term_key | default_text |
|----------|--------------|
| cod.useyn_n | No |
| cod.useyn_y | Yes |

---

## 2. msg. (77개)

| term_key |
|----------|
| msg.ai.input.required |
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
| msg.init.load.error |
| msg.load.error |
| msg.loading |
| msg.loading.wait |
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
| msg.ph.prompt |
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

### btn. (30개)

| term_key | default_text |
|----------|--------------|
| btn.apply | Apply |
| btn.cancel | Cancel |
| btn.color.hide | Hide Colors |
| btn.color.show | Show Colors |
| btn.colormap.hide | Hide Colormap |
| btn.colormap.show | Show Colormap |
| btn.delete | Delete |
| btn.login_btn | Login |
| btn.login.ing | Login in progress |
| btn.logout | Logout |
| btn.new | New |
| btn.object.manage | Object Manage |
| btn.objectconfig | Object Config |
| btn.ok | OK |
| btn.preview_btn | Preview |
| btn.prompt.replace | Replace Prompt |
| btn.register_btn | Register |
| btn.register.ing | Register Progressing |
| btn.reset.password | Reset Password |
| btn.reset.send | Send Reset Email |
| btn.sample.prompt | Sample Prompt |
| btn.save | Save |
| btn.savecols | Save Columns |
| btn.tab.close.left | Close Tabs to Left |
| btn.tab.close.others | Close Other Tabs |
| btn.tab.close.right | Close Tabs to Right |
| btn.tab.close.this | Close Tab |
| btn.template.edit | Template Edit |
| btn.upgrade | Upgrade |
| btn.upload_btn | Upload |

### lbl. (일반 레이블)

| term_key |
|----------|
| lbl.agree.all |
| lbl.align |
| lbl.bgcolor |
| lbl.billing.model |
| lbl.billing.multi |
| lbl.billing.single |
| lbl.bold |
| lbl.bordercolor |
| lbl.chapternm |
| lbl.chapterno |
| lbl.chart.type |
| lbl.codegroupcd_lbl |
| lbl.codevalue_lbl |
| lbl.color.ref |
| lbl.colnames |
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
| lbl.sentence.type |
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

### lbl.chart.legendpos.* — 범례 위치 옵션 (11개)

| term_key | default_text |
|----------|--------------|
| lbl.chart.legendpos.best | Auto |
| lbl.chart.legendpos.center | Center |
| lbl.chart.legendpos.center_left | Center Left |
| lbl.chart.legendpos.center_right | Center Right |
| lbl.chart.legendpos.lower_center | Lower Center |
| lbl.chart.legendpos.lower_left | Lower Left |
| lbl.chart.legendpos.lower_right | Lower Right |
| lbl.chart.legendpos.right | Right |
| lbl.chart.legendpos.upper_center | Upper Center |
| lbl.chart.legendpos.upper_left | Upper Left |
| lbl.chart.legendpos.upper_right | Upper Right |

### lbl.chart.linestyle.* — 선 스타일 옵션 (4개)

| term_key | default_text |
|----------|--------------|
| lbl.chart.linestyle.dash_dot | Dash-Dot |
| lbl.chart.linestyle.dashed | Dashed |
| lbl.chart.linestyle.dotted | Dotted |
| lbl.chart.linestyle.solid | Solid |

### lbl.chart.marker.* — 마커 모양 옵션 (4개)

| term_key | default_text |
|----------|--------------|
| lbl.chart.marker.circle | Circle |
| lbl.chart.marker.diamond | Diamond |
| lbl.chart.marker.square | Square |
| lbl.chart.marker.triangle | Triangle |

### lbl.chart.valueformat.* — 값 포맷 옵션 (3개)

| term_key | default_text |
|----------|--------------|
| lbl.chart.valueformat.percent | Percent |
| lbl.chart.valueformat.value | Value |
| lbl.chart.valueformat.value_percent | Value + Percent |

### lbl.chart.prop.* — 차트 속성 필드 레이블 (37개)

> `chart_definitions.py`의 각 property `term_key` 값. `MasterChartsPage` 설정 패널에 표시됨.

| term_key | default_text |
|----------|--------------|
| lbl.chart.prop.title | Chart Title |
| lbl.chart.prop.xField | X-Axis Field |
| lbl.chart.prop.xLabel | X-Axis Label |
| lbl.chart.prop.yField | Y-Axis Field |
| lbl.chart.prop.yLabel | Y-Axis Label |
| lbl.chart.prop.categoryField | Category |
| lbl.chart.prop.colorPalette | Color Theme |
| lbl.chart.prop.showDataLabels | Show Data Labels |
| lbl.chart.prop.barWidth | Bar Width |
| lbl.chart.prop.barGap | Bar Gap |
| lbl.chart.prop.legendPosition | Legend Position |
| lbl.chart.prop.showMarkers | Show Markers |
| lbl.chart.prop.lineStyle | Line Style |
| lbl.chart.prop.lineWidth | Line Width |
| lbl.chart.prop.marker | Marker Shape |
| lbl.chart.prop.markerSize | Marker Size |
| lbl.chart.prop.labelField | Label Field |
| lbl.chart.prop.valueField | Value Field |
| lbl.chart.prop.valueFormat | Value Format |
| lbl.chart.prop.cutout | Cutout (%) |
| lbl.chart.prop.sizeField | Size Field |
| lbl.chart.prop.showGroupLabels | Show Group Labels |
| lbl.chart.prop.bins | Bins |
| lbl.chart.prop.rwidth | Bar Width Ratio |
| lbl.chart.prop.notch | Notch |
| lbl.chart.prop.showMeans | Show Means |
| lbl.chart.prop.showFliers | Show Fliers |
| lbl.chart.prop.widths | Box Width |
| lbl.chart.prop.whis | Whisker Range |
| lbl.chart.prop.hbar.xField | Y-Axis Field (horizontalBar) |
| lbl.chart.prop.hbar.xLabel | Y-Axis Label (horizontalBar) |
| lbl.chart.prop.hbar.yField | X-Axis Field (horizontalBar) |
| lbl.chart.prop.hbar.yLabel | X-Axis Label (horizontalBar) |
| lbl.chart.prop.box.categoryField | X-Axis Field (box plot) |
| lbl.chart.prop.box.valueField | Y-Axis Field (box plot) |
| lbl.chart.prop.pareto.labelField | X-Axis Data (pareto) |
| lbl.chart.prop.pareto.yField | Y-Axis Data (pareto) |

### thd. (41개)

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
| thd.languagenm |
| thd.measureyn |
| thd.menucd_thd |
| thd.messagekey_thd |
| thd.messagetypecd_thd |
| thd.move |
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

### ttl. (34개)

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
| ttl.docselect |
| ttl.docselect.change |
| ttl.header.settings |
| ttl.list |
| ttl.login_ttl |
| ttl.myinfo.personal |
| ttl.myinfo.projects |
| ttl.myinfo.tenant |
| ttl.myinfo.tenant.history |
| ttl.myinfo.terms |
| ttl.preview.result |
| ttl.preview_ttl |
| ttl.prompt |
| ttl.prompt.desc |
| ttl.register_ttl |
| ttl.sample.list |
| ttl.sample.prompt |
| ttl.sentence.manage |
| ttl.table.manage |
| ttl.translations |
| ttl.value.settings |

### inf. (5개)

| term_key | default_text |
|----------|--------------|
| inf.gensentence.default | Analyze the data and write the results in a clear, descriptive sentence.\nData: {data}\nResult: |
| inf.iconnm_inf | Enter icon class name (e.g., HomeOutlined) |
| inf.password.hidden | * Existing password is not displayed |
| inf.preview.empty | No preview results. Click Preview button. |
| inf.preview.rows | Display Only 5 Rows |

---

## 요약

| prefix | 개수 |
|--------|------|
| cod.   | 32   |
| msg.   | 77   |
| mnu.   | 5    |
| btn.   | 30   |
| lbl.   | 139  |
| thd.   | 41   |
| ttl.   | 34   |
| inf.   | 5    |
| **합계** | **363** |

> lbl 139 = 일반 레이블 84 + legendpos 11 + linestyle 4 + marker 4 + valueformat 3 + chart.prop 37 - 중복 4(barWidth/barGap/bins/box.categoryField는 prop에 포함)  
> ※ DB 조회 결과(idx 0-99) 기준; lbl 일부는 기존 파일 유지

