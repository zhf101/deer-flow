"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import {
  Database,
  Eye,
  EyeOff,
  Lock,
  User,
  UserCheck,
  UserPlus,
  Workflow,
} from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { AuthPageShell } from "@/components/auth/auth-page-shell"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { getBrandingFromEnv } from "@/lib/branding"
import { apiRequest } from "@/lib/api-wrapper"
import { getApiUrl, getLegacyLoginUrl } from "@/lib/utils"
import { useI18n } from "@/contexts/i18n-context"
import { useSetupStatus } from "@/hooks/use-setup-status"

export function RegisterPage() {
  const branding = getBrandingFromEnv()
  const { t } = useI18n()
  const legacyLoginUrl = getLegacyLoginUrl()
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [formData, setFormData] = useState({
    username: "",
    password: "",
    confirmPassword: "",
  })

  const {
    isLoading: isStatusLoading,
    registrationEnabled,
  } = useSetupStatus({
    redirectToSetupIfNeeded: true,
  })

  useEffect(() => {
    if (isStatusLoading || registrationEnabled) {
      return
    }

    if (legacyLoginUrl) {
      window.location.replace(legacyLoginUrl)
      return
    }

    setError("本地注册已关闭，且未配置旧系统登录地址。")
  }, [isStatusLoading, legacyLoginUrl, registrationEnabled])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setSuccess("")

    if (formData.password !== formData.confirmPassword) {
      setError(t("register.alerts.password_mismatch"))
      return
    }

    if (formData.password.length < 6) {
      setError(t("register.alerts.password_too_short"))
      return
    }

    setIsLoading(true)

    try {
      const response = await apiRequest(`${getApiUrl()}/api/auth/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: formData.username,
          password: formData.password,
        }),
      })

      const data = await response.json()

      if (response.ok && data.success) {
        setSuccess(t("register.alerts.success"))
        setTimeout(() => {
          window.location.href = "/login"
        }, 2000)
      } else {
        setError(data.message || t("register.alerts.failed"))
      }
    } catch (registerError) {
      console.error("Registration failed:", registerError)
      setError(t("register.alerts.failed_retry"))
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
    if (success) {
      setSuccess("")
    }
  }

  const features = [
    {
      icon: Workflow,
      title: t("register.features.vbd.title"),
      description: t("register.features.vbd.description"),
    },
    {
      icon: Database,
      title: t("register.features.hitl.title"),
      description: t("register.features.hitl.description"),
    },
    {
      icon: UserCheck,
      title: t("register.features.timetravel.title"),
      description: t("register.features.timetravel.description"),
    },
  ]

  if (isStatusLoading) {
    return null
  }

  if (!registrationEnabled) {
    return (
      <AuthPageShell
        appName={branding.appName}
        logoPath={branding.logoPath}
        logoAlt={branding.logoAlt}
        leftDescription={
          process.env.NEXT_PUBLIC_APP_TAGLINE ? branding.tagline : t("branding.tagline")
        }
        mobileSubtitle="统一身份接入"
        features={features}
      >
        <Card className="p-8 bg-background/10 backdrop-blur-lg border-border shadow-2xl">
          <div className="space-y-4 text-center">
            <h2 className="text-2xl font-bold text-foreground">注册已关闭</h2>
            <p className="text-sm text-muted-foreground leading-6">
              {error || "正在跳转旧系统..."}
            </p>
            {legacyLoginUrl && !error ? (
              <div className="mx-auto h-8 w-8 rounded-full border-2 border-border border-t-primary animate-spin" />
            ) : (
              <Button
                type="button"
                className="w-full"
                disabled={!legacyLoginUrl}
                onClick={() => {
                  if (legacyLoginUrl) {
                    window.location.replace(legacyLoginUrl)
                  }
                }}
              >
                前往旧系统登录
              </Button>
            )}
          </div>
        </Card>
      </AuthPageShell>
    )
  }

  return (
    <AuthPageShell
      appName={branding.appName}
      logoPath={branding.logoPath}
      logoAlt={branding.logoAlt}
      leftDescription={
        process.env.NEXT_PUBLIC_APP_TAGLINE ? branding.tagline : t("branding.tagline")
      }
      mobileSubtitle={t("register.mobile_title")}
      features={features}
    >
      <Card className="p-8 bg-background/10 backdrop-blur-lg border-border shadow-2xl">
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-foreground mb-2">
            {t("register.title", { appName: branding.appName })}
          </h2>
          <p className="text-muted-foreground">{t("register.description")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <Alert className="border-red-200 bg-red-50">
              <AlertDescription className="text-red-800">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert className="border-green-200 bg-green-50">
              <AlertDescription className="text-green-800">
                {success}
              </AlertDescription>
            </Alert>
          )}

          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              {t("register.form.username")}
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="text"
                name="username"
                value={formData.username}
                onChange={handleInputChange}
                placeholder={t("register.form.username_placeholder")}
                className="pl-10 bg-background/10 border-border text-foreground placeholder:text-muted-foreground focus:border-primary"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              {t("register.form.password")}
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type={showPassword ? "text" : "password"}
                name="password"
                value={formData.password}
                onChange={handleInputChange}
                placeholder={t("register.form.password_placeholder")}
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

          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              {t("register.form.confirm_password")}
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type={showConfirmPassword ? "text" : "password"}
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleInputChange}
                placeholder={t("register.form.confirm_password_placeholder")}
                className="pl-10 pr-10 bg-background/10 border-border text-foreground placeholder:text-muted-foreground focus:border-primary"
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showConfirmPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          <Button
            type="submit"
            disabled={
              !formData.username ||
              !formData.password ||
              !formData.confirmPassword ||
              isLoading
            }
            className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-medium py-3 transition-all duration-200 transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
          >
            {isLoading ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                {t("register.form.submitting")}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <UserPlus className="h-4 w-4" />
                {t("register.form.submit")}
              </div>
            )}
          </Button>
        </form>

        <div className="mt-8 text-center">
          <p className="text-muted-foreground">
            {t("register.login_hint.has_account")}{" "}
            <Link
              href="/login"
              className="text-muted-foreground hover:text-foreground font-medium"
            >
              {t("register.login_hint.login_now")}
            </Link>
          </p>
        </div>
      </Card>

      <div className="mt-6 flex items-center justify-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-muted-foreground rounded-full animate-pulse" />
          <span className="text-muted-foreground">
            {t("register.status.agent_running")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-muted-foreground rounded-full animate-pulse" />
          <span className="text-muted-foreground">
            {t("register.status.open_register")}
          </span>
        </div>
      </div>
    </AuthPageShell>
  )
}
