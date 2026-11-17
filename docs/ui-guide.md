# Aviary: how to use the UI

This is a complete, self-contained description of the Aviary landing page and
the sign-in flows around it, written so that someone (or an assistant) who has
never seen it can operate it and explain it. It describes the page as built on
2026-11-16. It contains no passwords or keys.

Conventions used below: **bold** is text you see on screen; `code` is
something you type or a URL; "admin" means a Gitea site administrator (an
account with **Is Administrator** ticked in Gitea).

---

## 1. What Aviary is

Aviary is the front door of a small private Kubernetes cluster. One web page
lists every app the cluster serves, shows how much CPU, memory and disk each
is using, and has controls to open, scale, restart, stop and expose them. It
also has a shared chat-and-drawing box called the **whiteboard**.

- Landing page: `https://aviary.mesh.bmath.nyc/`
- Every app: `https://<name>.aviary.mesh.bmath.nyc/` (for example
  `https://gitea.aviary.mesh.bmath.nyc/`)
- Apps switched to "public" are also at `https://<name>.xdebbie.org/`

**You must be on the private network (the mesh) to use the internal names.**
If a browser shows "Secure Connection Failed" or a connection reset on an
`aviary.mesh.bmath.nyc` address, the machine's mesh tunnel is down. It is not
a certificate or app problem; bring the mesh back up and reload.

Certificates are issued by the cluster's own CA. Until a browser trusts that
CA it will warn about every page; see "CA certificate" in section 4.

---

## 2. Signing in and out

### 2.1 The front page (signed out)

Opening the landing page without a session shows a plain page: the word
**Aviary**, the hostname, a one-line fortune, a **Sign in** button, and a link
to the CA certificate. Nothing about the cluster is shown.

Click **Sign in**.

### 2.2 The sign-in form

You are sent to the identity provider (Gitea), restyled to look like Aviary:
the heading **Aviary** over a box titled **Sign In** with
**Username or Email Address**, **Password**, a **Remember This Device**
checkbox, a **Sign In** button, and a **Sign in with a passkey** link. The
address bar shows `gitea.aviary.mesh.bmath.nyc/user/login...`; that is
expected.

Enter a Gitea username and password and click **Sign In**. Accounts are
created by an admin; there is no self-registration.

The first time a given app asks to use your account, Gitea shows an
**Authorize Application** page. Approve it once; it does not ask again for
that app.

You land back on the landing page, signed in. Your username appears at the
top right.

### 2.3 How long a sign-in lasts

- The landing page session lasts **30 minutes**, then renews itself by passing
  through Gitea. While you are still signed in to Gitea this is invisible (the
  page may reload once). If you have signed out of Gitea, you get the sign-in
  form.
- A browser that has signed in before goes straight to Gitea when its session
  runs out, instead of showing the front page.
- Several Aviary tabs open at once are fine.

### 2.4 Signing out

Click **log out** at the top right of the landing page. The page says
**Logging out...** and then **Logged out.** It signs you out of three things:
the landing page, Gitea, and the login gate in front of each app. It offers
**Log in again**, and a fallback link **Log out of gitea** in case the Gitea
step did not take.

Signing out of Gitea alone does not end a landing-page session immediately;
it ends within 30 minutes.

### 2.5 One login for everything

Gitea is the single identity provider. How each app uses it:

| App | How you get in |
|---|---|
| Landing page, Drone, Harbor, mail (webmail) | Signs in with Gitea directly |
| jitsi, rustpad, cloudbeaver | A Gitea login gate in front of the app; any Gitea user |
| kubeshark, headlamp, grafana, velero, bash, garage, coredns-ui, cnpg-ui | A Gitea login gate that admits **admins only** |
| mattermost, argo | Their own separate logins (not on Gitea yet) |

After a gate lets you through, some apps still ask for a login of their own:
grafana, cnpg-ui (user `admin`), and argo.

If a gated admin-only app shows **RBAC: access denied**, you are signed in but
not an admin as the gate sees it. The gates cannot see Gitea's administrator
flag, only teams: they go by the `admins` team of the `aviary` organisation,
which is meant to hold exactly the site administrators. Team membership is
read when you sign in to the gate,
so after being added open `https://<app>.aviary.mesh.bmath.nyc/oauth2/logout`
once and then open the app again.

Admin sessions on the admin-only apps last about an hour and then pass
through Gitea again.

If an app shows **OAuth flow failed.** after signing in, open the app's
address again (not the long callback address in the bar); it will work.

---

## 3. The landing page at a glance

From top to bottom, when signed in:

1. **Header.** Top left: a button named like `ca.aviary.mesh.bmath.nyc.crt`.
   Top right: the hostname, your username, and **log out**.
2. **Title**: Aviary. (A brief splash of a birdcage shows for about three
   seconds when the page loads; wait for it to clear.)
3. **Two boxes side by side**: a fortune on the left, the **whiteboard** on
   the right.
4. **APPS**: one row ("tile") per app.
5. **SYSTEM**: one row per platform service.
6. **CLUSTER**: a table of the cluster's nodes.
7. **/etc/hosts**: lines to copy if your machine cannot resolve the names.
8. Footer: which pod served the page.

---

## 4. Header

- **CA certificate** (top-left button). Click to download the cluster's CA
  certificate. Import it into the browser or operating system trust store to
  stop certificate warnings on every Aviary address.
- **Username** and **log out** (top right). See section 2.4.

---

**Light and dark.** Under the account line in the top right corner is a link
reading **dark** (or **light**, when the page is already dark). It switches
the whole page between the light look and a black-and-cyan one. Until it is
clicked the page follows the system's light/dark setting; after that the
choice is remembered in that browser. The front page and the logged-out page
follow the same choice. Other apps (Gitea, Grafana and the rest) have their
own themes and are not affected.

## 5. The whiteboard

The box on the right is a shared chat room over a shared drawing surface.
Everyone on the page sees the same lines and the same drawing, live.

### 5.1 Talking

- Type in the line at the bottom of the box (placeholder
  **say something - <model> is listening** or **... is away**) and press
  Enter.
- Your line appears as `<yourname> text`. The room's AI model answers as
  `<its name> text`, written out as it is generated.
- Notices appear as `* text`, for example `* qwen is away: no GPU in the cluster`.
- The model can look things up while answering (read-only): the cluster's
  live state, and pages served inside the cluster. Each lookup shows as a line
  beginning with a middle dot, e.g. `· cluster: /api/v1/nodes`. It cannot change
  anything and has no internet access of its own.
- Lines are limited to 4,000 characters. The room keeps the last 300 lines in
  memory; a restart of the page empties it.

In the input, **Up** brings back what you typed before (newest first) and
**Down** goes forward again; this history is kept only while the page is
open. **Ctrl+L**, with the cursor in the input, clears the lines from your own view
as it would a terminal: the room keeps them (a reload brings them back),
the drawing stays, and nobody else's board changes. **Ctrl+P does nothing** anywhere on this page (it does not open the
print dialog); printing is still available from the browser's menu.

Commands, typed as a line:

| Command | Effect |
|---|---|
| `/clear` | Empties the whole board (lines and drawing) for everybody |
| `/erase` | Wipes the drawing only, keeps the lines |
| `/stop` (or press Escape while a reply is being written) | Cuts the model's reply short |
| `/k ...` | Reads the cluster the way `kubectl` would and posts the answer in the room as `<k>`. Read-only: `get`, `describe`, `logs`, `top`, `events`, `api-resources`. Without `-n` it looks in every namespace. Examples: `/k get pods -n aviary-gitea`, `/k get deploy`, `/k logs gitea-0 --tail 20`, `/k top nodes`. `/k` alone shows its usage. It cannot read Secrets or change anything. |

Clicking anywhere on the whiteboard puts the cursor in the input, so you
can just click and type. (Not while the marker is on, when a click draws,
and not when you are selecting text to copy.)

Web addresses in a line (anything starting `http://` or `https://`) are
links; they open in a new tab. While the marker is on, the drawing is on top
of the text, so turn the marker off to click one.

### 5.2 "Away"

The cluster's own model needs a GPU. When the cluster has none, the model is
marked away: the button at the bottom right reads **<name> (away)**, the box
says **<name> is away: no GPU in the cluster.**, and the first thing someone
says gets one `* <name> is away` notice. People can still talk to each other.
When a GPU returns the room says `* <name> is back`.

### 5.3 Drawing

- The small pencil at the bottom of the box is the **marker**. It grows when
  the pointer is over it. Click it to pick it up: the pointer becomes a
  crosshair over the board and the text dims.
- Press and drag on the board to draw. Each person's strokes have their own
  colour. A stroke is shared with everyone when you release the button.
- Click the marker again to put it down, so that clicks go to the text again.
- The **eraser** (the button beside the marker) wipes the drawing for
  everybody, after asking **Wipe the drawing for everyone? The lines stay.**
  Typing `/erase` does the same without asking. Neither removes the lines;
  `/clear` empties the whole board.
- The model does not see the drawing, only the text.

### 5.4 The model menu

Click the button at the bottom right of the whiteboard (the model's name with
a small triangle) to open the **Model** dialog.

- **The list** shows every model the room can use, each with **Use** (switch
  the room to it) or **in use**. Switching changes the model for everyone and
  posts a notice in the room. The first reply from a newly chosen model can
  take a while as it loads.
- If the list says **The cluster's own models are not available: there is no
  GPU for them to run on.**, that is the no-GPU state; nothing is broken.
- **Install line**: type a model name (`llama3.3:70b`, or
  `hf.co/user/repo:Q4_K_M`) and click **Install**. Progress shows underneath.
  This needs the cluster's model server to be running, so it needs a GPU.
- **API key box** (admins only): paste an Anthropic API key and click
  **Save**. The key is checked with Anthropic first; a rejected key is not
  kept. Once saved, `claude` appears in the list and can be chosen like any
  other model. Claude needs no GPU, so it is never away. The dialog afterwards
  shows only that a key is set and its last four characters. **Remove** takes
  the key, and Claude, back out. While Claude is the chosen model, what is
  said in the room is sent to Anthropic and replies are billed to that key.
- **Close** closes the dialog.

---

**none.** The last entry in the menu is **none**: no model answers. The room
stays open (people can talk, `/k` and the drawing work), the button reads
**no model**, and the input says *no model is listening*. Choosing it also
shuts the cluster's own model server (Ollama) off, by setting it to run no
pods, which frees its memory and GPU. While it is off the menu cannot list
Ollama's models; it shows the default one with the note *starts the
cluster's model server*, and choosing that starts it again (allow a minute or
more for the model to load). Choosing Claude leaves the server as it is.

## 6. The APPS list

Each row is one app. The columns, left to right:

| Column | Meaning |
|---|---|
| Name and description | The app. **Click anywhere on the row** (not only the name) to open the app, in the same tab. |
| **CPU now / max** | CPU in use now, then the most it has used in the last 7 days (its high-water mark). `35m` means 35 thousandths of a core; `1.7` means 1.7 cores. |
| **Mem now / max** | Memory in use now, then its 7-day high-water mark. |
| **Disk Cap** | Total size of the app's volumes. |
| **Disk Tput**, **Disk IOPS** | Not measured per app yet; shown as a dash. |

A number is coloured from blue (little) towards red (close to the app's
limit). Hover over a number for the detail.

Then the controls, left to right. Hover over any of them for a description.

| Control | Looks like | What it does |
|---|---|---|
| Scale | A red circle with **!** (some containers have no requests or limits set), or a grey circle with a double arrow | Opens the **Scale** dialog (section 6.1) |
| Stop / start | A square (stop) or a triangle (start) | Stop uninstalls the app but keeps its data volumes; the row greys out. Start reinstalls it and re-attaches the same volumes. Only shown for apps installed as a Helm release. |
| Restart | A circular arrow | Restarts every workload of the app (a rolling restart). |
| Images | Three horizontal lines | Opens the **Images** dialog (section 6.2) |
| **PRIVATE** switch | Blue when on | Whether the app is reachable on the private gateway (the `aviary.mesh.bmath.nyc` names). Turning it off makes the app unreachable from the mesh. |
| **PUBLIC** switch | Orange when on | Whether the app is reachable from the internet (the `xdebbie.org` names). Turning it on asks **Expose <app> on the public gateway?** first. |

After any control is used the page reloads within a couple of seconds. If the
change is not shown yet, reload once more.

### 6.1 The Scale dialog

Title: **Scale: <app>**. It has three parts.

**CPU** and **Memory** sliders. Each has two handles on one track:

- The **left handle is the request** (what each container is guaranteed), the
  **right handle is the limit** (the most it may use). The values are printed
  under the track as **request** and **limit**.
- These are defaults for containers in the app that do not set their own.
- The **coloured fill** on the track is the app's busiest container right now.
- The **red vertical line** is the high-water mark: the most any one container
  of the app has used in the last 7 days. The text above the track gives both
  figures. A limit should sit to the right of the red line.
- Drag the limit handle **all the way to the left** for no limit; it then
  reads **none**.

**Pods**. One line per workload of the app (its name, kind, and how many pods
are ready), each with a number box. Change a number to run more or fewer
copies of that workload; 0 stops it. The range is 0 to 10. A workload that
keeps data on a volume of its own usually cannot run more than one pod.

**restart the app now to apply the limits** (checkbox). New requests and
limits only apply to containers started afterwards; tick this to restart the
app straight away.

**Cancel** discards; **Apply** saves the limits, scales any workload whose
number changed, restarts if ticked, and returns to the page.

For an app installed by Helm, a later Helm upgrade puts the chart's own pod
counts back.

Details of the dialog worth knowing:

- **Apply is grey until the figures have loaded**, and goes grey again,
  reading **Applying…**, once pressed. Applying with a restart can take a
  while; the page reloads when it is done.
- **restart now** sits beside Apply. Ticked, every workload is rolled so
  running pods pick up the new requests and limits; unticked, they apply
  to pods started from then on.
- Each of **CPU** and **Memory** shows two pairs of figures: **app** (the
  whole app, now and high-water, the same numbers as on its tile) and
  **busiest container** (one container, now and high-water; the red line).
  They differ because a limit is per container while the tile adds up
  every container.
- **A request can be slid to 0** (the left thumb all the way down), as a
  limit can be slid to none: containers that set no request of their own
  are then promised nothing and are the first to be squeezed or evicted
  when a node runs short.
- A workload that **cannot run more than one pod is greyed out**, with the
  reason under its name: either its pods would share a volume only one of
  them can attach, or something else (an operator) sets its number. The
  server refuses more than one pod for these as well.

### 6.2 The Images dialog

Title: **Images: <app>**. Lists every workload in the app and the container
image each runs. For images that come from the cluster's own registry you can
pick another tag: **latest**, or one of the five most recently built. Choosing
one redeploys that workload on it. **Close** closes the dialog.

### 6.3 Rearranging the rows

Press on a row and drag it up or down to change the order; a blue line shows
where it will land. Rows stay within their own list (Apps or System). The
order is saved for you personally, the moment you drop, and follows your login
to any browser. Mouse only.

### 6.4 The apps

| Row | What it is | Notes |
|---|---|---|
| argo | Argo CD, continuous delivery | Its own login |
| cloudbeaver | Database client in the browser | After the Gitea gate you are signed in under your Gitea name. No connections are set up; add your own. |
| drone | Continuous integration | Builds run when code is pushed to Gitea. A build that sits waiting usually needs someone to press Approve in Drone. |
| gitea | Source code, and the identity provider | |
| harbor | Container image registry | For `docker login` use your Harbor username and the CLI secret from your Harbor user profile, not your Gitea password. |
| jitsi | Video meetings | |
| mail | Webmail (Axigen) for the domain `xdebbie.org` | Opens the mailbox `<your gitea name>@xdebbie.org`, which an admin must have created. Mail programs (IMAP, SMTP) use the mailbox's own password. |
| mattermost | Team chat | Its own login |
| rustpad | Shared text editor | Everyone with the same link edits the same pad. |

---

### 6.5 Where an app's entry comes from (AviaryApp)

A row exists because the app has a route on the gateway. What the row says
about it comes from an **AviaryApp** object in the cluster, named like the
tile (`kubectl get aviaryapps`):

| Field | Effect |
|---|---|
| `spec.description` | the line under the name |
| `spec.group` | `apps` or `system`: which list the row is in, and whether its link and controls are for admins only |
| `spec.web` | `false`: listed by name with no link (routed, but no page to open) |
| `spec.namespaces` | further namespaces counted on the tile and reached by its Scale popup and restart |

```yaml
apiVersion: aviary.xdebbie.org/v1alpha1
kind: AviaryApp
metadata:
  name: drone
spec:
  group: apps
  description: Continuous integration
  namespaces: [aviary-drone-builds]
```

Every field is optional and so is the object. Without one, the page falls
back to the route's `aviary/group` label, namespaces labelled
`aviary/app=<tile>`, and a list built into the page. A change shows within
about fifteen seconds. Only people who can change cluster-wide objects can
write these, which matters: moving an app from `system` to `apps` opens its
row's controls to everyone signed in.

### 6.6 Page-wide settings (AviaryConfig)

The page's own settings are one **AviaryConfig** object named `aviary`
(`kubectl get aviaryconfig`, `kubectl edit aviaryconfig aviary`):

| Field | Effect |
|---|---|
| `spec.session.minutes` | how long a sign-in to the landing page lasts (1 to 1440) |
| `spec.admin.team` | a Gitea team, `org:team`, whose members are admins here besides the site administrators; leave it out for site administrators only |
| `spec.scale.maxPods` | the most pods the Scale popup will set on one workload |
| `spec.chat.briefing` | what the whiteboard's model is told about this place |
| `status.chat.model` | the model chosen in the whiteboard's menu; the page writes this |

A change is picked up within about thirty seconds (a new session length
applies to sign-ins from then on). Anything the object leaves out comes
from the page's environment variables and the older `aviary-chat`
ConfigMap, so the page also runs without the object. Passwords and keys are
not kept here: they stay in Secrets.

## 7. The SYSTEM list

Platform services. The rows work like the Apps rows, with these differences:

- **For anyone who is not an admin the rows are greyed out**: no link, no
  controls. The apps behind them also refuse non-admins (section 2.5).
- They have no PRIVATE / PUBLIC switches, except **dns**.
- A row whose name is not a link is not a web page.

| Row | What it is |
|---|---|
| aviary | This page itself |
| bash | A shell inside the cluster, in the browser |
| cnpg-ui | Manages the PostgreSQL clusters run by CloudNativePG (currently Mattermost's database). Has its own login after the gate. Can create and delete databases. |
| coredns-ui | Console for the authoritative DNS server: metrics, logs, its configuration, restart and scale. Edits to the configuration are overwritten the next time the cluster's deployment is applied. |
| garage | Web UI for Garage, the cluster's S3-compatible object storage (buckets, keys, layout, object browser). Velero's backups are stored in it. |
| grafana | Metrics dashboards and alerting. Its own login after the gate. |
| headlamp | Kubernetes dashboard |
| kubeshark | Live view of network traffic between pods. It shows traffic in the clear, including tokens. |
| velero | Backup and restore. **Not a web page.** |
| dns | The authoritative DNS server (port 53). **Not a web page.** Its switches control whether it answers on the private and public gateways. |

---

## 8. The CLUSTER table

One row per node: **Node**, **Role**, **Ready**, **Kubelet** (version),
**CPU**, **Memory**, **Disk Cap**, **Disk Tput**, **Disk IOPS**. The numbers
refresh by themselves several times a second and are coloured by how busy the
node is.

A worker node that is not Ready gets a **delete** button (admins only). It
asks: **Delete node <name>? Its pods are force-deleted and its volume
attachments removed. Only do this if the machine is really gone.** It never
appears for a Ready node or a control-plane node.

---

## 9. /etc/hosts

A block of lines of the form `<address> <names...>`. If a machine on the mesh
cannot resolve the Aviary names, copy these lines into its `/etc/hosts` file.

---

## 10. Things that look like faults but are not

| What you see | What it means | What to do |
|---|---|---|
| "Secure Connection Failed" / connection reset on an internal name | The mesh tunnel on this machine is down | Bring the mesh up, reload |
| Certificate warnings everywhere | The browser does not trust the cluster's CA | Download and trust the CA (section 4) |
| **<model> is away** in the whiteboard | No GPU in the cluster | Nothing; or an admin can add an API key and switch the room to Claude |
| The model menu says the cluster's models are not available | Same: no GPU | Same |
| **RBAC: access denied** on an app | You are not an admin | Ask an admin; then use `/oauth2/logout` on that app and reopen it |
| **OAuth flow failed.** on an app | A stale sign-in attempt | Open the app's plain address again |
| The page reloads by itself | Your 30-minute session renewed | Nothing |
| A row's numbers show a dash | Nothing is running in that app, or metrics are not available yet | Wait, or check the app |
| A change you just made is not shown | The page's view of the cluster is refreshed in the background | Reload once |

---

## 11. Who can do what

| Action | Any signed-in user | Admin |
|---|---|---|
| See the page, open apps in the Apps list | Yes | Yes |
| Use the whiteboard, draw, switch the room's model | Yes | Yes |
| Scale, restart, stop/start, retag, expose an **app** | Yes | Yes |
| Open or control anything in **System** | No (greyed out) | Yes |
| Delete a dead node | No | Yes |
| Enter or remove the Anthropic API key | No | Yes |
| Rearrange your own rows | Yes | Yes |

Admins are Gitea's site administrators: in Gitea, **Site Administration >
Identity & Access > User Accounts**, edit the user, tick **Is
Administrator**. The landing page reads that flag when you sign in, so a
change takes effect at your next sign-in (at most 30 minutes, or log out and
in). The gated System apps go by the `aviary/admins` team instead (see 2.5).
