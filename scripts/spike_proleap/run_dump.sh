#!/usr/bin/env bash
#
# run_dump.sh —— DumpAsg 的瘦运行入口（spike 路线 A 验证）
#
# 用途：拼出 ProLeap 运行时 classpath（IntelliJ 自带 mvn 生成依赖清单 + 主 jar），
#       编译并运行 DumpAsg，把 ASG 导成 JSON。只做参数解析 + 调用，无业务逻辑。
#
# 对应设计文档：docs/调研/ProLeap解析器评估调研.md（§4 环境事实、§5 续接点）
#
# 用法：
#   scripts/spike_proleap/run_dump.sh [cob文件] [程序名] [格式] [输出json]
# 默认（不传参时）使用调研文档 §4 实测样本：
#   cob=/home/zp/Documents/cob/ZPOLDWNM.cob  程序名=ZPOLDWNM  格式=FIXED
#
set -euo pipefail

# —— 可配置参数（规范 §12：不硬编码，留默认但可覆盖）——
SRC_ROOT="/home/zp/Documents/cob/源码一期/源码"
COB="${1:-$SRC_ROOT/CBL FILES/ZPOLDWNM.cob}"
PROG="${2:-ZPOLDWNM}"
FMT="${3:-FIXED}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${4:-$HERE/asg_dump.json}"

# 拷贝簿目录：真实 CPY/CBL + 桩目录（顺序即查找优先级，真簿在前）
CPY_DIR="$SRC_ROOT/CPY FILES"
CBL_DIR="$SRC_ROOT/CBL FILES"
STUB_DIR="$HERE/stub_copybooks"
COPY_DIRS="$CPY_DIR:$CBL_DIR:$STUB_DIR"

PROLEAP_REPO="/home/zp/langgraph/proleap-cobol-parser"
PROLEAP_JAR="$PROLEAP_REPO/target/proleap-cobol-parser-4.0.0.jar"
MVN="/opt/idea-IU-261.23567.138/plugins/maven/lib/maven3/bin/mvn"
# 本机仅 IntelliJ JBR 带 javac（JDK21），统一用它编译+运行，版本一致
JBR="/opt/idea-IU-261.23567.138/jbr/bin"
DEP_PLUGIN="org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath"
CP_FILE="$HERE/.classpath.txt"

[ -f "$PROLEAP_JAR" ] || { echo "缺主 jar: $PROLEAP_JAR（先在 $PROLEAP_REPO 构建）" >&2; exit 1; }
[ -x "$MVN" ] || { echo "缺 mvn: $MVN" >&2; exit 1; }
[ -x "$JBR/javac" ] || { echo "缺 javac: $JBR/javac" >&2; exit 1; }

# —— 1. 生成依赖 classpath（缓存，避免每次跑 mvn）——
# 用插件全坐标调用，绕开 'dependency' 前缀解析（离线优先，失败回退在线）
if [ ! -f "$CP_FILE" ]; then
  echo "[run_dump] 生成依赖 classpath（首次，经 maven-dependency-plugin:build-classpath）..."
  ( cd "$PROLEAP_REPO" && "$MVN" -q -o "$DEP_PLUGIN" \
      "-Dmdep.outputFile=$CP_FILE" -DincludeScope=runtime ) \
    || ( cd "$PROLEAP_REPO" && "$MVN" -q "$DEP_PLUGIN" \
           "-Dmdep.outputFile=$CP_FILE" -DincludeScope=runtime )
fi
DEPS="$(cat "$CP_FILE")"
CP="$DEPS:$PROLEAP_JAR:$HERE"

# —— 2. 源清理（去变更标记 + 停用行）——
CLEAN="$HERE/cleaned_$PROG.cob"
echo "[run_dump] 清理源 -> $CLEAN"
python3 "$HERE/clean_source.py" "$COB" "$CLEAN"

# —— 3. 生成缺失拷贝簿的最小桩（基于清理后源的 COPY 集）——
echo "[run_dump] 生成缺失拷贝簿桩 -> $STUB_DIR"
python3 "$HERE/gen_stub_copybooks.py" "$CLEAN" "$STUB_DIR" "$CPY_DIR" "$CBL_DIR"

# —— 4. 编译 ——
echo "[run_dump] javac DumpAsg.java"
"$JBR/javac" -cp "$CP" -d "$HERE" "$HERE/DumpAsg.java"

# —— 5. 运行（解析清理后的源）——
echo "[run_dump] 解析 $CLEAN （程序 $PROG / 格式 $FMT；拷贝簿 3 目录）"
"$JBR/java" -cp "$CP" DumpAsg "$CLEAN" "$PROG" "$FMT" "$OUT" "$COPY_DIRS"
