import uiautomation as auto, ctypes
u = ctypes.windll.user32
print("=== TOP-LEVEL WINDOWS (filtered) ===")
want = ('AIComposer','Chrome','Gemini','NotebookLM','Grok','摘要','分镜','YT 工具')
n=0
for w in auto.GetRootControl().GetChildren():
    nm=(w.Name or '').strip()
    if nm and any(k in nm for k in want):
        r=w.BoundingRectangle
        print(f"{w.ControlTypeName:14} | hwnd={w.NativeWindowHandle} | {nm!r} | {r.left},{r.top},{r.width()}x{r.height()}")
        n+=1
print(f"matched {n} windows")
print()
print("=== ALL top-level names (first 50 non-empty) ===")
c=0
for i,w in enumerate(auto.GetRootControl().GetChildren()):
    nm=(w.Name or '').strip()
    if nm:
        print(f"  {w.ControlTypeName:14} | {nm!r}")
        c+=1
    if c>=50: break
