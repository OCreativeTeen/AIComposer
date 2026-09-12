"""Grok Imagine image+video automation without SCENE GUI."""

from __future__ import annotations

from pathlib import Path


def run_grok_imagine(
    video_detail: dict,
    n: int,
    *,
    video_nb_index: int,
    visual_style: str = "",
    host_narrator: str = "",
) -> tuple[str, list[dict]]:
    """Open N Imagine tabs, paste cover, generate image then video (no auto-download).

    Returns ``(summary_message, video_results)``. Video failures per scene do not
    abort the run — tabs are left for manual review before ``grvc`` / ``gvd``.
    """
    import config
    import config_prompt
    from cli.browser_tasks import (
        GROK_IMAGINE_URL,
        _chrome_cdp_user_data_dir,
        _grok_prepare_all_tabs_cdp,
        _grok_resolve_cover_png,
        _grok_scene_image_prompts,
        ensure_grok_cdp,
        format_grok_video_results_summary,
        log,
        resolve_chrome_profile_directory,
    )
    from storyproducer.prompts import build_grok_video_prompts

    if n < 1:
        raise RuntimeError("还没有 scene_content。请先 scnge → scnsave。")
    v_idx = int(video_nb_index)
    v_label = config_prompt.grok_scene_video_nb_choice_label(v_idx)
    grok_port = ensure_grok_cdp(GROK_IMAGINE_URL)
    profile_dir = resolve_chrome_profile_directory(
        getattr(config, "GEMINI_CHROME_PROFILE", "")
    )
    profile_label = (getattr(config, "GEMINI_CHROME_PROFILE", "") or profile_dir).strip()
    user_data = _chrome_cdp_user_data_dir()
    log(
        f"[storyproducer] Grok Imagine × {n} cdp_port={grok_port} "
        f"account={profile_label!r} profile={profile_dir} user-data={user_data}"
    )
    cover_png = _grok_resolve_cover_png()
    if not cover_png:
        raise RuntimeError("没有封面图。请先 itc 选封面，再 grv。")
    scene_prompts = _grok_scene_image_prompts(n)
    video_prompts = build_grok_video_prompts(
        video_detail,
        n,
        video_nb_index=v_idx,
        visual_style=visual_style,
        host_narrator=host_narrator,
    )
    for i, (_lbl, text) in enumerate(video_prompts, 1):
        log(f"[storyproducer] Grok scene {i} video prompt ready ({len(text)} chars)")
    pasted_n, prompt_n, _downloads, video_results = _grok_prepare_all_tabs_cdp(
        n,
        cover_png=cover_png,
        port=grok_port,
        fresh_tabs=True,
        scene_prompts=scene_prompts,
        auto_generate=True,
        video_prompts=video_prompts,
        auto_generate_video=True,
        auto_download_video=False,
    )
    if pasted_n < n:
        raise RuntimeError(f"第一轮只成功粘贴 {pasted_n}/{n} 个标签的封面图。")
    if prompt_n < n:
        raise RuntimeError(f"只成功粘贴 {prompt_n}/{n} 个场景提示词。")
    review = format_grok_video_results_summary(video_results, n=n)
    detail = (
        f"opened {n} Grok Imagine tab(s) for {profile_label!r} "
        f"cdp={grok_port}; video_nb={v_idx} ({v_label})\n{review}"
    )
    return detail, video_results
