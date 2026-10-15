from app.services.diff_parser import count_file_diff, parse_unified_diff

MODIFIED_DIFF = """diff --git a/pkg/calc.py b/pkg/calc.py
index 111..222 100644
--- a/pkg/calc.py
+++ b/pkg/calc.py
@@ -1,4 +1,5 @@
 import math
+import json
 
 def total(values):
@@ -10,7 +11,7 @@ def total(values):
     if not values:
         return 0
-    return sum(values)
+    return math.fsum(values)
 def helper(x):
     return x
"""

ADDED_DIFF = """diff --git a/new_mod.py b/new_mod.py
new file mode 100644
index 000..333
--- /dev/null
+++ b/new_mod.py
@@ -0,0 +1,3 @@
+def fresh():
+    return 1
+
"""

DELETED_DIFF = """diff --git a/old_mod.py b/old_mod.py
deleted file mode 100644
index 444..000
--- a/old_mod.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def gone():
-    return 2
"""

RENAME_DIFF = """diff --git a/old_name.py b/new_name.py
similarity index 92%
rename from old_name.py
rename to new_name.py
index 555..666 100644
--- a/old_name.py
+++ b/new_name.py
@@ -1,3 +1,3 @@
 def same():
-    return 1
+    return 2
"""

BINARY_DIFF = """diff --git a/logo.png b/logo.png
index 777..888 100644
Binary files a/logo.png and b/logo.png differ
"""


def test_parses_modified_file_lines():
    files = parse_unified_diff(MODIFIED_DIFF)
    assert len(files) == 1
    f = files[0]
    assert f.path == "pkg/calc.py"
    assert f.change_type == "modified"
    assert f.added_lines == {2: "import json", 13: "    return math.fsum(values)"}
    assert f.removed_lines == {12: "    return sum(values)"}
    assert 1 in f.context_lines_new


def test_parses_added_file():
    files = parse_unified_diff(ADDED_DIFF)
    f = files[0]
    assert f.change_type == "added"
    assert f.path == "new_mod.py"
    assert sorted(f.added_lines) == [1, 2, 3]
    assert f.removed_lines == {}


def test_parses_deleted_file():
    files = parse_unified_diff(DELETED_DIFF)
    f = files[0]
    assert f.change_type == "deleted"
    assert f.removed_lines == {1: "def gone():", 2: "    return 2"}


def test_parses_rename_with_hunk():
    files = parse_unified_diff(RENAME_DIFF)
    f = files[0]
    assert f.change_type == "renamed"
    assert f.old_path == "old_name.py"
    assert f.path == "new_name.py"
    assert f.added_lines == {2: "    return 2"}
    assert f.removed_lines == {2: "    return 1"}


def test_parses_binary_file():
    files = parse_unified_diff(BINARY_DIFF)
    assert files[0].is_binary is True
    assert files[0].added_lines == {}


def test_count_file_diff():
    files = parse_unified_diff(MODIFIED_DIFF)
    assert count_file_diff(files[0]) == 3


def test_empty_diff_returns_empty():
    assert parse_unified_diff("") == []
