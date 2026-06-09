# industry_map — A股产业链地图 数据库+截图+Web 全套
"""
三层解耦架构：
  industry_map/db.py          → 数据库读写（CRUD + 查询）  
  industry_map/render.py      → 从DB读取数据，渲染HTML流程图
  industry_map/screenshot.py  → 截图 + 发送（chromium headless）
  industry_map/update.py      → 数据更新（从行情API补充行业/概念信息）
  
数据流：行情API → update.py → astock_data.db → render.py → HTML → screenshot.py → PNG
                                                  → web版直接查DB展示
"""
