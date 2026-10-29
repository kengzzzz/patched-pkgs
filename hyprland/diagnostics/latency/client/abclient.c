#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/timerfd.h>
#include <time.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <gbm.h>
#include <linux/udmabuf.h>
#include <wayland-client.h>

#include "linux-dmabuf-v1-client-protocol.h"
#include "presentation-time-client-protocol.h"
#include "tearing-control-v1-client-protocol.h"
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include "xdg-shell-client-protocol.h"

#define NBUFS 4

static struct {
    struct wl_display                    *display;
    struct wl_compositor                 *compositor;
    struct wl_subcompositor              *subcompositor;
    struct wl_shm                        *shm;
    struct wl_seat                       *seat;
    struct wl_pointer                    *pointer;
    struct xdg_wm_base                   *wm_base;
    struct zwp_linux_dmabuf_v1           *dmabuf;
    struct wp_presentation               *presentation;
    struct zwlr_layer_shell_v1           *layer_shell;
    struct wp_tearing_control_manager_v1 *tearing;
} g;

static FILE                 *outf;
static volatile sig_atomic_t running = 1;

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

static void die(const char *msg) {
    fprintf(stderr, "abclient: %s: %s\n", msg, strerror(errno));
    exit(1);
}

static void on_signal(int sig) {
    (void)sig;
    running = 0;
}

/* hide the cursor over our surfaces, a visible hardware cursor blocks tearing */

static void ptr_enter(void *data, struct wl_pointer *p, uint32_t serial, struct wl_surface *s, wl_fixed_t x, wl_fixed_t y) {
    (void)data, (void)s, (void)x, (void)y;
    wl_pointer_set_cursor(p, serial, NULL, 0, 0);
}
static void ptr_leave(void *d, struct wl_pointer *p, uint32_t serial, struct wl_surface *s) {
    (void)d, (void)p, (void)serial, (void)s;
}
static void ptr_motion(void *d, struct wl_pointer *p, uint32_t t, wl_fixed_t x, wl_fixed_t y) {
    (void)d, (void)p, (void)t, (void)x, (void)y;
}
static void ptr_button(void *d, struct wl_pointer *p, uint32_t serial, uint32_t t, uint32_t b, uint32_t st) {
    (void)d, (void)p, (void)serial, (void)t, (void)b, (void)st;
}
static void ptr_axis(void *d, struct wl_pointer *p, uint32_t t, uint32_t a, wl_fixed_t v) {
    (void)d, (void)p, (void)t, (void)a, (void)v;
}
static void ptr_frame(void *d, struct wl_pointer *p) {
    (void)d, (void)p;
}
static void ptr_axis_source(void *d, struct wl_pointer *p, uint32_t s) {
    (void)d, (void)p, (void)s;
}
static void ptr_axis_stop(void *d, struct wl_pointer *p, uint32_t t, uint32_t a) {
    (void)d, (void)p, (void)t, (void)a;
}
static void ptr_axis_discrete(void *d, struct wl_pointer *p, uint32_t a, int32_t v) {
    (void)d, (void)p, (void)a, (void)v;
}

static const struct wl_pointer_listener ptr_listener = {
    .enter = ptr_enter, .leave = ptr_leave, .motion = ptr_motion, .button = ptr_button, .axis = ptr_axis,
    .frame = ptr_frame, .axis_source = ptr_axis_source, .axis_stop = ptr_axis_stop, .axis_discrete = ptr_axis_discrete,
};

static void seat_caps(void *data, struct wl_seat *seat, uint32_t caps) {
    (void)data;
    if ((caps & WL_SEAT_CAPABILITY_POINTER) && !g.pointer) {
        g.pointer = wl_seat_get_pointer(seat);
        wl_pointer_add_listener(g.pointer, &ptr_listener, NULL);
    }
}
static void seat_name(void *data, struct wl_seat *seat, const char *name) {
    (void)data, (void)seat, (void)name;
}

static const struct wl_seat_listener seat_listener = {seat_caps, seat_name};

static void registry_global(void *data, struct wl_registry *reg, uint32_t name, const char *iface, uint32_t ver) {
    (void)data;
    if (!strcmp(iface, wl_compositor_interface.name))
        g.compositor = wl_registry_bind(reg, name, &wl_compositor_interface, ver < 4 ? ver : 4);
    else if (!strcmp(iface, wl_subcompositor_interface.name))
        g.subcompositor = wl_registry_bind(reg, name, &wl_subcompositor_interface, 1);
    else if (!strcmp(iface, wl_shm_interface.name))
        g.shm = wl_registry_bind(reg, name, &wl_shm_interface, 1);
    else if (!strcmp(iface, wl_seat_interface.name) && !g.seat) {
        g.seat = wl_registry_bind(reg, name, &wl_seat_interface, ver < 5 ? ver : 5);
        wl_seat_add_listener(g.seat, &seat_listener, NULL);
    } else if (!strcmp(iface, xdg_wm_base_interface.name))
        g.wm_base = wl_registry_bind(reg, name, &xdg_wm_base_interface, 1);
    else if (!strcmp(iface, zwp_linux_dmabuf_v1_interface.name) && ver >= 3)
        g.dmabuf = wl_registry_bind(reg, name, &zwp_linux_dmabuf_v1_interface, 3);
    else if (!strcmp(iface, wp_presentation_interface.name))
        g.presentation = wl_registry_bind(reg, name, &wp_presentation_interface, 1);
    else if (!strcmp(iface, zwlr_layer_shell_v1_interface.name))
        g.layer_shell = wl_registry_bind(reg, name, &zwlr_layer_shell_v1_interface, ver < 4 ? ver : 4);
    else if (!strcmp(iface, wp_tearing_control_manager_v1_interface.name))
        g.tearing = wl_registry_bind(reg, name, &wp_tearing_control_manager_v1_interface, 1);
}

static void registry_remove(void *data, struct wl_registry *reg, uint32_t name) {
    (void)data, (void)reg, (void)name;
}

static const struct wl_registry_listener registry_listener = {registry_global, registry_remove};

static void wm_ping(void *data, struct xdg_wm_base *b, uint32_t serial) {
    (void)data;
    xdg_wm_base_pong(b, serial);
}

static const struct xdg_wm_base_listener wm_listener = {wm_ping};

static void fill_pattern(uint8_t *map, int w, int h, int stride, bool black) {
    for (int y = 0; y < h; y++) {
        uint32_t *row = (uint32_t *)(map + (size_t)y * stride);
        for (int x = 0; x < w; x++)
            row[x] = black ? 0xff000000u : 0xff000000u | ((x * 255 / w) << 16) | ((y * 255 / h) << 8) | 0x60;
    }
}

static struct wl_buffer *shm_buffer(int w, int h, uint32_t argb) {
    int    stride = w * 4;
    size_t size   = (size_t)stride * h;
    int    fd     = memfd_create("abshm", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, size) < 0)
        die("shm memfd");
    uint32_t *map = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED)
        die("shm mmap");
    if (argb)
        for (size_t i = 0; i < size / 4; i++)
            map[i] = argb;
    else
        fill_pattern((uint8_t *)map, w, h, stride, false);
    munmap(map, size);
    struct wl_shm_pool *pool = wl_shm_create_pool(g.shm, fd, size);
    struct wl_buffer   *buf  = wl_shm_pool_create_buffer(pool, 0, w, h, stride, WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool);
    close(fd);
    return buf;
}

/* game: a fullscreen client that presents a new buffer every frame, optionally from a subsurface like Wine.
 * Without --fps it draws on frame callbacks like a vsync game, with --fps it commits on a timer like a game
 * with vsync off. */

struct gbuf {
    struct wl_buffer *wl;
    struct gbm_bo    *bo;
    bool              busy;
};

struct feedback {
    uint64_t commit_ns;
    uint64_t frame;
};

static struct {
    struct wl_surface    *top, *content;
    struct wl_subsurface *sub;
    struct xdg_surface   *xs;
    struct xdg_toplevel  *tl;
    int                   w, h, cfg_w, cfg_h;
    bool                  configured, waiting;
    struct gbuf           bufs[NBUFS];
    uint32_t              format;
    bool                  subsurface, fullscreen, black, tear, full_damage, use_shm;
    const char           *gbm_path;
    struct gbm_device    *gbm;
    double                fps;
    uint64_t              frames, skipped;
    int                   udmabuf;
} game;

static void buf_release(void *data, struct wl_buffer *b);
static void draw(void);

static const struct wl_buffer_listener buf_listener = {buf_release};

static void free_buffers(void) {
    for (int i = 0; i < NBUFS; i++) {
        if (game.bufs[i].wl)
            wl_buffer_destroy(game.bufs[i].wl);
        if (game.bufs[i].bo)
            gbm_bo_destroy(game.bufs[i].bo);
        game.bufs[i] = (struct gbuf){0};
    }
}

static struct wl_buffer *udmabuf_buffer(int w, int h) {
    int    stride = (w * 4 + 255) & ~255;
    size_t size   = ((size_t)stride * h + 4095) & ~(size_t)4095;
    int    memfd  = memfd_create("abdmabuf", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    if (memfd < 0 || ftruncate(memfd, size) < 0 || fcntl(memfd, F_ADD_SEALS, F_SEAL_SHRINK) < 0)
        die("dmabuf memfd");
    uint8_t *map = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, 0);
    if (map == MAP_FAILED)
        die("dmabuf mmap");
    fill_pattern(map, w, h, stride, game.black);
    munmap(map, size);

    struct udmabuf_create c  = {.memfd = memfd, .flags = UDMABUF_FLAGS_CLOEXEC, .offset = 0, .size = size};
    int                   fd = ioctl(game.udmabuf, UDMABUF_CREATE, &c);
    if (fd < 0)
        die("UDMABUF_CREATE");
    close(memfd);

    struct zwp_linux_buffer_params_v1 *params = zwp_linux_dmabuf_v1_create_params(g.dmabuf);
    zwp_linux_buffer_params_v1_add(params, fd, 0, 0, stride, DRM_FORMAT_MOD_LINEAR >> 32, DRM_FORMAT_MOD_LINEAR & 0xffffffff);
    struct wl_buffer *buf = zwp_linux_buffer_params_v1_create_immed(params, w, h, game.format, 0);
    zwp_linux_buffer_params_v1_destroy(params);
    close(fd);
    return buf;
}

static struct wl_buffer *gbm_buffer(int w, int h, struct gbm_bo **out_bo) {
    struct gbm_bo *bo = gbm_bo_create(game.gbm, w, h, game.format, GBM_BO_USE_SCANOUT | GBM_BO_USE_RENDERING);
    if (!bo)
        bo = gbm_bo_create(game.gbm, w, h, game.format, GBM_BO_USE_SCANOUT);
    if (!bo)
        die("gbm_bo_create");

    uint32_t mstride = 0;
    void    *mdata   = NULL;
    uint8_t *map     = gbm_bo_map(bo, 0, 0, w, h, GBM_BO_TRANSFER_WRITE, &mstride, &mdata);
    if (map) {
        fill_pattern(map, w, h, mstride, game.black);
        gbm_bo_unmap(bo, mdata);
    } else
        fprintf(stderr, "abclient: gbm_bo_map failed, buffer content is undefined\n");

    uint64_t                           mod    = gbm_bo_get_modifier(bo);
    int                                planes = gbm_bo_get_plane_count(bo);
    struct zwp_linux_buffer_params_v1 *params = zwp_linux_dmabuf_v1_create_params(g.dmabuf);
    for (int p = 0; p < planes; p++) {
        int fd = gbm_bo_get_fd_for_plane(bo, p);
        if (fd < 0)
            die("gbm_bo_get_fd_for_plane");
        zwp_linux_buffer_params_v1_add(params, fd, p, gbm_bo_get_offset(bo, p), gbm_bo_get_stride_for_plane(bo, p), mod >> 32, mod & 0xffffffff);
        close(fd);
    }
    struct wl_buffer *buf = zwp_linux_buffer_params_v1_create_immed(params, w, h, game.format, 0);
    zwp_linux_buffer_params_v1_destroy(params);
    fprintf(outf, "M modifier 0x%016lx planes %d mapped %d\n", mod, planes, map != NULL);
    *out_bo = bo;
    return buf;
}

static void alloc_buffers(int w, int h) {
    free_buffers();
    for (int i = 0; i < NBUFS; i++) {
        if (game.use_shm)
            game.bufs[i].wl = shm_buffer(w, h, 0);
        else if (game.gbm)
            game.bufs[i].wl = gbm_buffer(w, h, &game.bufs[i].bo);
        else
            game.bufs[i].wl = udmabuf_buffer(w, h);
        wl_buffer_add_listener(game.bufs[i].wl, &buf_listener, &game.bufs[i]);
    }
    game.w = w;
    game.h = h;
}

static void buf_release(void *data, struct wl_buffer *b) {
    (void)b;
    struct gbuf *buf = data;
    buf->busy        = false;
    if (game.waiting && game.fps <= 0) {
        game.waiting = false;
        draw();
    }
}

static void fb_sync_output(void *data, struct wp_presentation_feedback *f, struct wl_output *o) {
    (void)data, (void)f, (void)o;
}

static void fb_presented(void *data, struct wp_presentation_feedback *f, uint32_t sec_hi, uint32_t sec_lo, uint32_t nsec, uint32_t refresh, uint32_t seq_hi,
                         uint32_t seq_lo, uint32_t flags) {
    struct feedback *fb   = data;
    uint64_t         recv = now_ns();
    uint64_t         t    = (((uint64_t)sec_hi << 32) | sec_lo) * 1000000000ull + nsec;
    uint64_t         seq  = ((uint64_t)seq_hi << 32) | seq_lo;
    fprintf(outf, "P %lu %lu %lu %u %lu %u %lu\n", fb->frame, fb->commit_ns, t, refresh, seq, flags, recv);
    wp_presentation_feedback_destroy(f);
    free(fb);
}

static void fb_discarded(void *data, struct wp_presentation_feedback *f) {
    struct feedback *fb = data;
    fprintf(outf, "D %lu %lu %lu\n", fb->frame, fb->commit_ns, now_ns());
    wp_presentation_feedback_destroy(f);
    free(fb);
}

static const struct wp_presentation_feedback_listener fb_listener = {fb_sync_output, fb_presented, fb_discarded};

static void frame_done(void *data, struct wl_callback *cb, uint32_t t) {
    (void)data, (void)t;
    wl_callback_destroy(cb);
    draw();
}

static const struct wl_callback_listener frame_listener = {frame_done};

static void draw(void) {
    if (!game.configured)
        return;
    struct gbuf *buf = NULL;
    for (int i = 0; i < NBUFS; i++) {
        if (!game.bufs[i].busy) {
            buf = &game.bufs[i];
            break;
        }
    }
    if (!buf) {
        game.waiting = true;
        game.skipped++;
        return;
    }

    buf->busy = true;
    wl_surface_attach(game.content, buf->wl, 0, 0);
    if (game.frames == 0 || game.full_damage)
        wl_surface_damage_buffer(game.content, 0, 0, INT32_MAX, INT32_MAX);
    else
        wl_surface_damage_buffer(game.content, (game.frames * 64) % (game.w - 64), 0, 64, 64);

    if (game.fps <= 0) {
        struct wl_callback *cb = wl_surface_frame(game.content);
        wl_callback_add_listener(cb, &frame_listener, NULL);
    }

    struct feedback *fb = calloc(1, sizeof(*fb));
    fb->frame           = game.frames;
    struct wp_presentation_feedback *pf = wp_presentation_feedback(g.presentation, game.content);
    wp_presentation_feedback_add_listener(pf, &fb_listener, fb);

    fb->commit_ns = now_ns();
    wl_surface_commit(game.content);
    game.frames++;
}

static void tl_configure(void *data, struct xdg_toplevel *tl, int32_t w, int32_t h, struct wl_array *states) {
    (void)data, (void)tl, (void)states;
    game.cfg_w = w;
    game.cfg_h = h;
}

static void tl_close(void *data, struct xdg_toplevel *tl) {
    (void)data, (void)tl;
    running = 0;
}

static const struct xdg_toplevel_listener tl_listener = {tl_configure, tl_close};

static void xs_configure(void *data, struct xdg_surface *xs, uint32_t serial) {
    (void)data;
    int w = game.cfg_w > 0 ? game.cfg_w : 1280;
    int h = game.cfg_h > 0 ? game.cfg_h : 720;
    xdg_surface_ack_configure(xs, serial);

    if (game.configured && w == game.w && h == game.h)
        return;

    fprintf(outf, "C %lu %d %d\n", now_ns(), w, h);
    alloc_buffers(w, h);

    struct wl_region *opaque = wl_compositor_create_region(g.compositor);
    wl_region_add(opaque, 0, 0, w, h);
    wl_surface_set_opaque_region(game.content, opaque);
    if (game.subsurface)
        wl_surface_set_opaque_region(game.top, opaque);
    wl_region_destroy(opaque);

    if (game.subsurface) {
        wl_surface_attach(game.top, shm_buffer(w, h, 0xff000000), 0, 0);
        wl_surface_damage_buffer(game.top, 0, 0, INT32_MAX, INT32_MAX);
    }

    bool first      = !game.configured;
    game.configured = true;
    if (first || game.subsurface)
        draw();
    if (game.subsurface)
        wl_surface_commit(game.top);
}

static const struct xdg_surface_listener xs_listener = {xs_configure};

static int run_game(void) {
    if (!g.presentation || (!game.use_shm && !g.dmabuf))
        die("compositor lacks linux-dmabuf v3 or presentation-time");
    if (game.gbm_path && !game.use_shm) {
        int fd = open(game.gbm_path, O_RDWR | O_CLOEXEC);
        if (fd < 0)
            die(game.gbm_path);
        game.gbm = gbm_create_device(fd);
        if (!game.gbm)
            die("gbm_create_device");
    } else if (!game.use_shm) {
        game.udmabuf = open("/dev/udmabuf", O_RDWR | O_CLOEXEC);
        if (game.udmabuf < 0)
            die("/dev/udmabuf");
    }

    game.top     = wl_compositor_create_surface(g.compositor);
    game.content = game.top;
    if (game.subsurface) {
        game.content = wl_compositor_create_surface(g.compositor);
        game.sub     = wl_subcompositor_get_subsurface(g.subcompositor, game.content, game.top);
        wl_subsurface_set_desync(game.sub);
    }

    game.xs = xdg_wm_base_get_xdg_surface(g.wm_base, game.top);
    xdg_surface_add_listener(game.xs, &xs_listener, NULL);
    game.tl = xdg_surface_get_toplevel(game.xs);
    xdg_toplevel_add_listener(game.tl, &tl_listener, NULL);
    xdg_toplevel_set_title(game.tl, "abgame");
    xdg_toplevel_set_app_id(game.tl, "abgame");
    if (game.fullscreen)
        xdg_toplevel_set_fullscreen(game.tl, NULL);
    // Hyprland binds the hint to a window when the tearing control is created, so the toplevel has to exist first
    if (game.tear) {
        if (!g.tearing)
            die("no tearing control");
        struct wp_tearing_control_v1 *tc = wp_tearing_control_manager_v1_get_tearing_control(g.tearing, game.content);
        wp_tearing_control_v1_set_presentation_hint(tc, WP_TEARING_CONTROL_V1_PRESENTATION_HINT_ASYNC);
    }
    wl_surface_commit(game.top);
    return 0;
}

/* osd: a layer surface that maps and unmaps on a schedule, like a volume OSD */

static struct {
    enum zwlr_layer_shell_v1_layer layer;
    int                            on_ms, off_ms, cycles, delay_ms;
    struct wl_surface             *surface;
    struct zwlr_layer_surface_v1  *ls;
    struct wl_buffer              *buf;
    bool                           mapped;
    int                            cycle;
    uint64_t                       next_ns;
} osd;

static void ls_configure(void *data, struct zwlr_layer_surface_v1 *ls, uint32_t serial, uint32_t w, uint32_t h) {
    (void)data, (void)w, (void)h;
    zwlr_layer_surface_v1_ack_configure(ls, serial);
    if (osd.mapped)
        return;
    wl_surface_attach(osd.surface, osd.buf, 0, 0);
    wl_surface_damage_buffer(osd.surface, 0, 0, INT32_MAX, INT32_MAX);
    wl_surface_commit(osd.surface);
    osd.mapped = true;
    fprintf(outf, "MAP %d %lu\n", osd.cycle, now_ns());
}

static void ls_closed(void *data, struct zwlr_layer_surface_v1 *ls) {
    (void)data, (void)ls;
}

static const struct zwlr_layer_surface_v1_listener ls_listener = {ls_configure, ls_closed};

static void osd_show(void) {
    osd.surface = wl_compositor_create_surface(g.compositor);
    osd.ls      = zwlr_layer_shell_v1_get_layer_surface(g.layer_shell, osd.surface, NULL, osd.layer, "abosd");
    zwlr_layer_surface_v1_add_listener(osd.ls, &ls_listener, NULL);
    zwlr_layer_surface_v1_set_size(osd.ls, 400, 120);
    zwlr_layer_surface_v1_set_anchor(osd.ls, ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP);
    zwlr_layer_surface_v1_set_margin(osd.ls, 40, 0, 0, 0);
    wl_surface_commit(osd.surface);
}

static void osd_hide(void) {
    zwlr_layer_surface_v1_destroy(osd.ls);
    wl_surface_destroy(osd.surface);
    osd.ls      = NULL;
    osd.surface = NULL;
    osd.mapped  = false;
    fprintf(outf, "UNMAP %d %lu\n", osd.cycle, now_ns());
}

static void osd_tick(void) {
    uint64_t t = now_ns();
    if (t < osd.next_ns)
        return;
    if (osd.surface) {
        osd_hide();
        osd.cycle++;
        osd.next_ns = t + (uint64_t)osd.off_ms * 1000000ull;
        if (osd.cycle >= osd.cycles)
            running = 0;
    } else {
        osd_show();
        osd.next_ns = t + (uint64_t)osd.on_ms * 1000000ull;
    }
}

static int run_osd(void) {
    if (!g.layer_shell)
        die("no layer shell");
    osd.buf     = shm_buffer(400, 120, 0xffff8000);
    osd.next_ns = now_ns() + (uint64_t)osd.delay_ms * 1000000ull;
    return 0;
}

static uint32_t parse_format(const char *s) {
    if (!strcmp(s, "xr24"))
        return DRM_FORMAT_XRGB8888;
    if (!strcmp(s, "xb24"))
        return DRM_FORMAT_XBGR8888;
    if (!strcmp(s, "ar24"))
        return DRM_FORMAT_ARGB8888;
    if (!strcmp(s, "ab24"))
        return DRM_FORMAT_ABGR8888;
    fprintf(stderr, "unknown format %s\n", s);
    exit(2);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: abclient game|osd [options]\n");
        return 2;
    }
    bool is_game = !strcmp(argv[1], "game");
    if (!is_game && strcmp(argv[1], "osd"))
        return 2;

    outf        = stdout;
    game.format = DRM_FORMAT_XBGR8888;
    osd.layer   = ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY;
    osd.on_ms   = 1500;
    osd.off_ms  = 3500;
    osd.cycles  = 1;
    double secs = 0;

    static const struct option opts[] = {
        {"format", required_argument, 0, 'f'},  {"subsurface", no_argument, 0, 's'},  {"fullscreen", no_argument, 0, 'F'}, {"black", no_argument, 0, 'b'},
        {"tear", no_argument, 0, 't'},           {"full-damage", no_argument, 0, 'D'}, {"gbm", required_argument, 0, 'g'},  {"shm", no_argument, 0, 'm'},
        {"fps", required_argument, 0, 'r'},      {"seconds", required_argument, 0, 'S'}, {"layer", required_argument, 0, 'l'}, {"on", required_argument, 0, 'o'},
        {"off", required_argument, 0, 'O'},      {"cycles", required_argument, 0, 'c'}, {"delay", required_argument, 0, 'd'}, {"log", required_argument, 0, 'L'},
        {0, 0, 0, 0}};
    int c;
    optind = 2;
    while ((c = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (c) {
            case 'f': game.format = parse_format(optarg); break;
            case 's': game.subsurface = true; break;
            case 'F': game.fullscreen = true; break;
            case 'b': game.black = true; break;
            case 't': game.tear = true; break;
            case 'D': game.full_damage = true; break;
            case 'g': game.gbm_path = optarg; break;
            case 'm': game.use_shm = true; break;
            case 'r': game.fps = atof(optarg); break;
            case 'S': secs = atof(optarg); break;
            case 'l': osd.layer = !strcmp(optarg, "top") ? ZWLR_LAYER_SHELL_V1_LAYER_TOP : ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY; break;
            case 'o': osd.on_ms = atoi(optarg); break;
            case 'O': osd.off_ms = atoi(optarg); break;
            case 'c': osd.cycles = atoi(optarg); break;
            case 'd': osd.delay_ms = atoi(optarg); break;
            case 'L':
                outf = fopen(optarg, "w");
                if (!outf)
                    die("log");
                break;
            default: return 2;
        }
    }
    setvbuf(outf, NULL, _IOLBF, 0);

    struct sigaction sa = {.sa_handler = on_signal};
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    g.display = wl_display_connect(NULL);
    if (!g.display)
        die("wl_display_connect");
    struct wl_registry *reg = wl_display_get_registry(g.display);
    wl_registry_add_listener(reg, &registry_listener, NULL);
    wl_display_roundtrip(g.display);
    if (!g.compositor || !g.wm_base || !g.shm)
        die("missing core globals");
    xdg_wm_base_add_listener(g.wm_base, &wm_listener, NULL);

    if (is_game)
        run_game();
    else
        run_osd();

    int tfd = -1;
    if (is_game && game.fps > 0) {
        tfd = timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC);
        if (tfd < 0)
            die("timerfd_create");
        uint64_t          period = (uint64_t)(1e9 / game.fps);
        struct itimerspec its    = {.it_interval = {period / 1000000000ull, period % 1000000000ull}, .it_value = {0, 1000000}};
        timerfd_settime(tfd, 0, &its, NULL);
    }

    uint64_t end = secs > 0 ? now_ns() + (uint64_t)(secs * 1e9) : UINT64_MAX;
    while (running && now_ns() < end) {
        while (wl_display_prepare_read(g.display) != 0)
            wl_display_dispatch_pending(g.display);
        wl_display_flush(g.display);
        struct pollfd p[2] = {{wl_display_get_fd(g.display), POLLIN, 0}, {tfd, POLLIN, 0}};
        int           r    = poll(p, tfd >= 0 ? 2 : 1, 5);
        if (r > 0 && (p[0].revents & POLLIN)) {
            if (wl_display_read_events(g.display) < 0)
                die("read_events");
        } else
            wl_display_cancel_read(g.display);
        if (wl_display_dispatch_pending(g.display) < 0)
            die("dispatch");
        if (tfd >= 0 && r > 0 && (p[1].revents & POLLIN)) {
            uint64_t n;
            if (read(tfd, &n, sizeof(n)) == sizeof(n))
                draw();
        }
        if (!is_game)
            osd_tick();
    }
    if (!is_game && osd.surface)
        osd_hide();
    wl_display_roundtrip(g.display);
    fprintf(outf, "END %lu frames %lu skipped %lu\n", now_ns(), game.frames, game.skipped);
    return 0;
}
