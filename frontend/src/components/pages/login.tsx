"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import {
  Database,
  Eye,
  EyeOff,
  Lock,
  LogIn,
  User,
  UserCheck,
  Workflow,
} from "lucide-react"

import { AuthPageShell } from "@/components/auth/auth-page-shell"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { AUTH_CACHE_KEY } from "@/lib/auth-cache"
import { getBrandingFromEnv } from "@/lib/branding"
import { apiRequest } from "@/lib/api-wrapper"
import { getApiUrl, getLegacyLoginUrl } from "@/lib/utils"
import { useI18n } from "@/contexts/i18n-context"
import { useSetupStatus } from "@/hooks/use-setup-status"

type LoginStage = "checking" | "redirecting" | "local" | "error"

export function LoginPage() {
  const branding = getBrandingFromEnv()
  const { t } = useI18n()
  const searchParams = useSearchParams()
  const legacyLoginUrl = getLegacyLoginUrl()
  const legacyToken = searchParams.get("token")

  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [stage, setStage] = useState<LoginStage>(legacyToken ? "checking" : "local")
  const [message, setMessage] = useState("正在验证旧系统登录状态...")
  const [formData, setFormData] = useState({
    username: "",
    password: "",
  })

  const { isLoading: isStatusLoading, registrationEnabled } = useSetupStatus({
    redirectToSetupIfNeeded: true,
  })

  useEffect(() => {
    if (legacyToken) {
      return
    }

    if (isStatusLoading) {
      setStage("checking")
      return
    }

    if (registrationEnabled) {
      setStage("local")
      return
    }

    if (!legacyLoginUrl) {
      setStage("error")
      setMessage("未配置旧系统登录地址，请联系管理员。")
      return
    }

    setStage("redirecting")
    setMessage("本地登录已关闭，正在跳转旧系统...")
    window.location.replace(legacyLoginUrl)
  }, [isStatusLoading, legacyLoginUrl, legacyToken, registrationEnabled])

  useEffect(() => {
    if (!legacyToken) {
      return
    }

    let cancelled = false

    const loginWithLegacyToken = async () => {
      try {
        const response = await fetch(`${getApiUrl()}/api/auth/sso/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ token: legacyToken }),
        })

        const data = await response.json().catch(() => null)
        if (!response.ok || !data?.success) {
          throw new Error(data?.detail || data?.message || "旧系统登录校验失败")
        }

        const userData = {
          id: data.user.id,
          username: data.user.username,
          is_admin: data.user.is_admin,
        }

        localStorage.removeItem("auth_token")
        localStorage.removeItem("auth_user")
        localStorage.setItem("auth_token", data.access_token)
        localStorage.setItem("auth_user", JSON.stringify(userData))
        localStorage.setItem(
          AUTH_CACHE_KEY,
          JSON.stringify({
            user: userData,
            token: data.access_token,
            refreshToken: data.refresh_token,
            expiresAt: Date.now() + (data.expires_in || 1800) * 1000,
            refreshExpiresAt: Date.now() + (data.refresh_expires_in || 604800) * 1000,
            timestamp: Date.now(),
          })
        )

        window.location.replace("/task")
      } catch (ssoError) {
        if (!cancelled) {
          setStage("error")
          setMessage(
            ssoError instanceof Error ? ssoError.message : "旧系统登录校验失败"
          )
        }
      }
    }

    void loginWithLegacyToken()

    return () => {
      cancelled = true
    }
  }, [legacyToken])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsLoading(true)

    try {
      const response = await apiRequest(`${getApiUrl()}/api/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: formData.username,
          password: formData.password,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        const userData = {
          id: data.user.id,
          username: data.user.username,
          is_admin: data.user.is_admin,
        }

        localStorage.setItem("auth_token", data.access_token)
        localStorage.setItem("auth_user", JSON.stringify(userData))
        localStorage.setItem(
          AUTH_CACHE_KEY,
          JSON.stringify({
            user: userData,
            token: data.access_token,
            refreshToken: data.refresh_token,
            expiresAt: Date.now() + (data.expires_in || 1800) * 1000,
            refreshExpiresAt: Date.now() + (data.refresh_expires_in || 604800) * 1000,
            timestamp: Date.now(),
          })
        )

        window.location.href = "/task"
      } else {
        setError(t("login.alerts.auth_failed"))
      }
    } catch (loginError) {
      console.error("Login failed:", loginError)
      setError(t("login.alerts.network_failed"))
    } finally {
      setIsLoading(false)
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
    if (error) {
      setError("")
    }
  }

  const features = [
    {
      icon: Workflow,
      title: t("login.features.version_control.title"),
      description: t("login.features.version_control.description"),
    },
    {
      icon: Database,
      title: t("login.features.team.title"),
      description: t("login.features.team.description"),
    },
    {
      icon: UserCheck,
      title: t("login.features.automation.title"),
      description: t("login.features.automation.description"),
    },
  ]

  return (
    <AuthPageShell
      appName={branding.appName}
      logoPath={branding.logoPath}
      logoAlt={branding.logoAlt}
      leftDescription={
        process.env.NEXT_PUBLIC_APP_TAGLINE ? branding.tagline : t("branding.tagline")
      }
      mobileSubtitle={
        legacyToken ? "旧系统单点登录" : t("login.mobile_title")
      }
      features={features}
    >
      <Card className="p-8 bg-background/10 backdrop-blur-lg border-border shadow-2xl">
        {stage === "checking" || stage === "redirecting" || stage === "error" ? (
          <div className="space-y-4 text-center">
            <h2 className="text-2xl font-bold text-foreground">登录处理中</h2>
            <p className="text-sm text-muted-foreground leading-6">{message}</p>
            {stage === "checking" || stage === "redirecting" ? (
              <div className="mx-auto h-8 w-8 rounded-full border-2 border-border border-t-primary animate-spin" />
            ) : null}
            {stage === "error" ? (
              <Button
                type="button"
                className="w-full"
                onClick={() => {
                  if (legacyLoginUrl) {
                    window.location.replace(legacyLoginUrl)
                  }
                }}
                disabled={!legacyLoginUrl}
              >
                前往旧系统登录
              </Button>
            ) : null}
          </div>
        ) : (
          <>
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-foreground mb-2">
                {t("login.title", { appName: branding.appName })}
              </h2>
              <p className="text-muted-foreground">{t("login.description")}</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="p-3 rounded-lg bg-destructive/20 border border-destructive/50">
                  <p className="text-sm text-destructive-foreground">{error}</p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-2">
                  {t("login.form.username")}
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="text"
                    name="username"
                    value={formData.username}
                    onChange={handleInputChange}
                    placeholder={t("login.form.username_placeholder")}
                    className="pl-10 bg-background/10 border-border text-foreground placeholder:text-muted-foreground focus:border-primary"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-2">
                  {t("login.form.password")}
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type={showPassword ? "text" : "password"}
                    name="password"
                    value={formData.password}
                    onChange={handleInputChange}
                    placeholder={t("login.form.password_placeholder")}
                    className="pl-10 pr-10 bg-background/10 border-border text-foreground placeholder:text-muted-foreground focus:border-primary"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center text-muted-foreground">
                  <input type="checkbox" className="rounded mr-2" />
                  {t("login.options.remember_me")}
                </label>
                <a href="#" className="text-muted-foreground hover:text-foreground">
                  {t("login.options.forgot_password")}
                </a>
              </div>

              <Button
                type="submit"
                disabled={!formData.username || !formData.password || isLoading}
                className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-medium py-3 transition-all duration-200 transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
              >
                {isLoading ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                    {t("login.form.submitting")}
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <LogIn className="h-4 w-4" />
                    {t("login.form.submit")}
                  </div>
                )}
              </Button>
            </form>

            <div className="mt-8 text-center">
              <p className="text-muted-foreground">
                {registrationEnabled ? (
                  <>
                    {t("login.register_prompt")}{" "}
                    <Link
                      href="/register"
                      className="text-muted-foreground hover:text-foreground font-medium"
                    >
                      {t("login.register_link")}
                    </Link>
                  </>
                ) : (
                  <>{t("login.register_closed")}</>
                )}
              </p>
            </div>
          </>
        )}
      </Card>
    </AuthPageShell>
  )
}
