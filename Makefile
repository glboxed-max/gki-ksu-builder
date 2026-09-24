.PHONY: test lint compile plan clean

test:            ## 跑单元测试（本地秒级）
	python -m unittest discover -s tests -v

lint:            ## 语法与静态检查
	python -m compileall -q kbx tests .github/scripts scripts
	python -m ruff check kbx tests .github/scripts scripts 2>/dev/null || true

check: test lint   ## 跑测试 + 工作流自检
	python scripts/check_workflows.py

compile:         ## 只做语法检查
	python -m compileall -q kbx tests

plan:            ## 示例：看 6.1 + 全功能会做什么
	python -m kbx plan --android android14 --kernel 6.1 --sub-level 138 \
		--ksu sukisu-13000 --with susfs,kpm,zram_enhanced,bbg,ntsync,net_enhanced,rekernel

clean:
	rm -rf build dist .pytest_cache **/__pycache__
