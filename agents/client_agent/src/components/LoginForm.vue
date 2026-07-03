<template>
  <div class="login-form">
    <h2>FDE AI Desktop</h2>
    <p class="subtitle">Sign in to your FDE Platform account</p>

    <label>Server URL</label>
    <input v-model="server" placeholder="https://217.142.246.70:8443/api" />

    <label>Username</label>
    <input v-model="username" placeholder="admin" />

    <label>Password</label>
    <input v-model="password" type="password" @keyup.enter="login" />

    <p v-if="error" class="error">{{ error }}</p>

    <button @click="login" :disabled="loading">
      {{ loading ? "Signing in..." : "Sign In" }}
    </button>
  </div>
</template>

<script>
import { ref } from "vue";

export default {
  name: "LoginForm",
  emits: ["authenticated"],
  setup(props, { emit }) {
    const server = ref(localStorage.getItem("fde_server_url") || "https://217.142.246.70:8443/api");
    const username = ref("");
    const password = ref("");
    const loading = ref(false);
    const error = ref("");

    const login = async () => {
      if (!username.value || !password.value) {
        error.value = "Username and password required";
        return;
      }

      loading.value = true;
      error.value = "";

      try {
        const formData = new URLSearchParams();
        formData.append("username", username.value);
        formData.append("password", password.value);

        const response = await fetch(`${server.value}/auth/token`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: formData,
        });

        if (!response.ok) {
          const msg = await response.text();
          throw new Error(msg || `HTTP ${response.status}`);
        }

        const data = await response.json();
        const token = data.access_token;

        localStorage.setItem("fde_server_url", server.value);
        emit("authenticated", token);
      } catch (e) {
        error.value = e.message || "Authentication failed";
      } finally {
        loading.value = false;
      }
    };

    return { server, username, password, loading, error, login };
  },
};
</script>

<style scoped>
.login-form {
  display: flex;
  flex-direction: column;
  padding: 32px 24px;
  gap: 8px;
}
h2 { font-size: 20px; color: #e0e0e0; }
.subtitle { font-size: 12px; color: #888; margin-bottom: 12px; }
label { font-size: 12px; color: #aaa; }
input {
  padding: 10px;
  border: 1px solid #444;
  border-radius: 6px;
  background: #1a1a2e;
  color: #e0e0e0;
  font-size: 14px;
}
input:focus { outline: none; border-color: #1a73e8; }
button {
  margin-top: 12px;
  padding: 10px;
  border: none;
  border-radius: 6px;
  background: #1a73e8;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}
button:disabled { opacity: 0.6; cursor: default; }
.error { color: #ff6b6b; font-size: 12px; }
</style>