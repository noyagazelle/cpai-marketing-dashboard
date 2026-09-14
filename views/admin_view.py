"""Manage access — invite teammates by email; they set their own password when
they register. Only shown once login is active (someone has registered or has
a pending invite)."""
import streamlit as st

import config


def render(current_username: str):
    st.subheader("Manage access")
    st.caption("Invite a teammate by email — they'll choose their own username and password "
               "the first time they visit the app. Changes apply immediately.")

    users = config.auth_users() or {"usernames": {}}
    usernames = users.setdefault("usernames", {})
    pending = config.pre_authorized_emails()

    st.markdown("**Active users**")
    if not usernames:
        st.caption("No one has registered yet.")
    for uname, info in list(usernames.items()):
        display_name = (f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                         or info.get("name") or uname)
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{uname}** — {display_name}")
        if uname == current_username:
            c2.caption("(you)")
        elif c2.button("Remove", key=f"remove_user_{uname}"):
            del usernames[uname]
            config.set_auth_users(users)
            st.rerun()

    st.markdown("**Pending invites**")
    if not pending:
        st.caption("No pending invites.")
    for email in list(pending):
        c1, c2 = st.columns([4, 1])
        c1.write(email)
        if c2.button("Cancel", key=f"cancel_invite_{email}"):
            pending.remove(email)
            config.set_pre_authorized_emails(pending)
            st.rerun()

    st.divider()
    st.markdown("**Invite a teammate**")
    with st.form("invite_form", clear_on_submit=True):
        new_email = st.text_input("Their email")
        submitted = st.form_submit_button("Send invite")

    if submitted:
        new_email = new_email.strip().lower()
        if not new_email or "@" not in new_email:
            st.error("Enter a valid email address.")
        elif new_email in pending:
            st.error(f"{new_email} is already invited.")
        elif any(info.get("email") == new_email for info in usernames.values()):
            st.error(f"{new_email} already has an account.")
        else:
            pending.append(new_email)
            config.set_pre_authorized_emails(pending)
            st.rerun()
