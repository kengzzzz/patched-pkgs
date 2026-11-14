// lockclient: requests an ext-session-lock-v1 lock and logs what the compositor answers.
// SIGUSR1 sends unlock_and_destroy. Never run it on the live session.
#define _GNU_SOURCE
#include <errno.h>
#include <getopt.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/signalfd.h>
#include <time.h>
#include <unistd.h>

#include <wayland-client.h>

#include "ext-session-lock-v1-client-protocol.h"

#define MAX_OUTPUTS 8

struct output {
    struct wl_output                   *output;
    struct wl_surface                  *surface;
    struct ext_session_lock_surface_v1 *lock_surface;
    struct wl_buffer                   *buffer;
};

static struct {
    struct wl_display                *display;
    struct wl_compositor             *compositor;
    struct wl_shm                    *shm;
    struct ext_session_lock_manager_v1 *manager;
    struct ext_session_lock_v1       *lock;
    struct output                     outputs[MAX_OUTPUTS];
    int                               n_outputs;
    bool                              draw;
    bool                              unlocked;
} g = {.draw = true};

static FILE *logf_;

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

static void logev(const char *what) {
    fprintf(logf_, "%s %llu\n", what, (unsigned long long)now_ns());
    fflush(logf_);
}

static void die(const char *msg) {
    fprintf(stderr, "lockclient: %s: %s\n", msg, strerror(errno));
    exit(1);
}

static struct wl_buffer *make_buffer(int w, int h) {
    int stride = w * 4, size = stride * h;
    int fd     = memfd_create("lockclient", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, size) < 0)
        die("memfd");
    uint32_t *px = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (px == MAP_FAILED)
        die("mmap");
    for (int i = 0; i < w * h; i++)
        px[i] = 0xff602020;
    munmap(px, size);
    struct wl_shm_pool *pool = wl_shm_create_pool(g.shm, fd, size);
    struct wl_buffer   *buf  = wl_shm_pool_create_buffer(pool, 0, w, h, stride, WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool);
    close(fd);
    return buf;
}

static void surface_configure(void *data, struct ext_session_lock_surface_v1 *ls, uint32_t serial, uint32_t w, uint32_t h) {
    struct output *o = data;
    ext_session_lock_surface_v1_ack_configure(ls, serial);
    if (o->buffer)
        wl_buffer_destroy(o->buffer);
    o->buffer = make_buffer(w, h);
    wl_surface_attach(o->surface, o->buffer, 0, 0);
    wl_surface_damage_buffer(o->surface, 0, 0, INT32_MAX, INT32_MAX);
    wl_surface_commit(o->surface);
}

static const struct ext_session_lock_surface_v1_listener surface_listener = {.configure = surface_configure};

static void lock_locked(void *data, struct ext_session_lock_v1 *l) {
    logev("LOCKED");
}

static void lock_finished(void *data, struct ext_session_lock_v1 *l) {
    logev("FINISHED");
}

static const struct ext_session_lock_v1_listener lock_listener = {.locked = lock_locked, .finished = lock_finished};

static void reg_global(void *data, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
    if (!strcmp(iface, wl_compositor_interface.name))
        g.compositor = wl_registry_bind(r, name, &wl_compositor_interface, 4);
    else if (!strcmp(iface, wl_shm_interface.name))
        g.shm = wl_registry_bind(r, name, &wl_shm_interface, 1);
    else if (!strcmp(iface, ext_session_lock_manager_v1_interface.name))
        g.manager = wl_registry_bind(r, name, &ext_session_lock_manager_v1_interface, 1);
    else if (!strcmp(iface, wl_output_interface.name) && g.n_outputs < MAX_OUTPUTS)
        g.outputs[g.n_outputs++].output = wl_registry_bind(r, name, &wl_output_interface, 1);
}

static void reg_remove(void *data, struct wl_registry *r, uint32_t name) {}

static const struct wl_registry_listener reg_listener = {.global = reg_global, .global_remove = reg_remove};

static void unlock(void) {
    if (g.unlocked)
        return;
    g.unlocked = true;
    ext_session_lock_v1_unlock_and_destroy(g.lock);
    wl_display_roundtrip(g.display);
    logev("UNLOCK");
}

static void usage(void) {
    fprintf(stderr, "usage: lockclient --log FILE [--no-draw] [--unlock-after MS] [--seconds N]\n");
    exit(2);
}

int main(int argc, char **argv) {
    const char *log_path = NULL;
    long        unlock_after = -1, seconds = 60;
    static const struct option opts[] = {
        {"log", required_argument, 0, 'l'},
        {"no-draw", no_argument, 0, 'n'},
        {"unlock-after", required_argument, 0, 'u'},
        {"seconds", required_argument, 0, 's'},
        {0, 0, 0, 0},
    };
    for (int c; (c = getopt_long(argc, argv, "", opts, NULL)) != -1;) {
        switch (c) {
            case 'l': log_path = optarg; break;
            case 'n': g.draw = false; break;
            case 'u': unlock_after = atol(optarg); break;
            case 's': seconds = atol(optarg); break;
            default: usage();
        }
    }
    if (!log_path)
        usage();
    logf_ = fopen(log_path, "a");
    if (!logf_)
        die("log");

    sigset_t mask;
    sigemptyset(&mask);
    sigaddset(&mask, SIGUSR1);
    sigprocmask(SIG_BLOCK, &mask, NULL);
    int sfd = signalfd(-1, &mask, SFD_CLOEXEC);
    if (sfd < 0)
        die("signalfd");

    g.display = wl_display_connect(NULL);
    if (!g.display)
        die("connect");
    wl_registry_add_listener(wl_display_get_registry(g.display), &reg_listener, NULL);
    wl_display_roundtrip(g.display);
    if (!g.compositor || !g.shm || !g.manager) {
        fprintf(stderr, "lockclient: missing globals\n");
        logev("NOGLOBAL");
        return 1;
    }

    g.lock = ext_session_lock_manager_v1_lock(g.manager);
    ext_session_lock_v1_add_listener(g.lock, &lock_listener, NULL);
    logev("REQUEST");
    if (g.draw) {
        for (int i = 0; i < g.n_outputs; i++) {
            struct output *o = &g.outputs[i];
            o->surface       = wl_compositor_create_surface(g.compositor);
            o->lock_surface  = ext_session_lock_v1_get_lock_surface(g.lock, o->surface, o->output);
            ext_session_lock_surface_v1_add_listener(o->lock_surface, &surface_listener, o);
        }
    }

    const uint64_t start    = now_ns();
    const uint64_t deadline = start + (uint64_t)seconds * 1000000000ull;
    const uint64_t unlock_t = unlock_after >= 0 ? start + (uint64_t)unlock_after * 1000000ull : UINT64_MAX;
    int            fd       = wl_display_get_fd(g.display);

    for (;;) {
        while (wl_display_prepare_read(g.display) != 0)
            wl_display_dispatch_pending(g.display);
        wl_display_flush(g.display);

        uint64_t t    = now_ns();
        uint64_t next = unlock_t < deadline ? unlock_t : deadline;
        int      ms   = next > t ? (int)((next - t) / 1000000ull) + 1 : 0;

        struct pollfd p[2] = {{.fd = fd, .events = POLLIN}, {.fd = sfd, .events = POLLIN}};
        int           r    = poll(p, 2, ms);
        if (r < 0 && errno != EINTR) {
            wl_display_cancel_read(g.display);
            die("poll");
        }
        if (r > 0 && (p[0].revents & POLLIN)) {
            if (wl_display_read_events(g.display) < 0)
                break;
        } else
            wl_display_cancel_read(g.display);
        if (wl_display_dispatch_pending(g.display) < 0)
            break;

        if (r > 0 && (p[1].revents & POLLIN)) {
            struct signalfd_siginfo si;
            if (read(sfd, &si, sizeof(si)) == sizeof(si) && si.ssi_signo == SIGUSR1) {
                unlock();
                break;
            }
        }
        t = now_ns();
        if (t >= unlock_t && !g.unlocked) {
            unlock();
            break;
        }
        if (t >= deadline)
            break;
    }

    logev("EXIT");
    wl_display_disconnect(g.display);
    return 0;
}
