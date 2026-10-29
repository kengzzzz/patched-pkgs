hl.monitor({
    output   = "",
    mode     = "1280x720@60",
    position = "auto",
    scale    = 1,
})

hl.config({
    ecosystem = {
        no_update_news    = true,
        no_donation_nag   = true,
    },
    misc = {
        disable_hyprland_logo           = true,
        disable_splash_rendering        = true,
        disable_hyprland_guiutils_check = true,
        disable_autoreload              = true,
        background_color                = 0x203040,
    },
    animations = {
        enabled = false,
    },
    decoration = {
        blur   = { enabled = false },
        shadow = { enabled = false },
    },
    cursor = {
        invisible = true,
    },
    render = {
        direct_scanout = 1,
    },
    debug = {
        disable_logs = false,
    },
})
