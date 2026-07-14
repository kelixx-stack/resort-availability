terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# =================================================================
# 1. 입력 변수 정의 (Variables)
# =================================================================

variable "aws_region" {
  type        = string
  default     = "ap-northeast-2"
  description = "AWS 배포 리전 (서울 리전 기본값)"
}

variable "project_name" {
  type        = string
  default     = "resort-automation"
  description = "프로젝트 고유 이름 식별자"
}

variable "environment" {
  type        = string
  default     = "prod"
  description = "배포 환경 단계"
}

variable "admin_email" {
  type        = string
  default     = "admin@example.com" # 배포 시 실제 본인의 이메일로 변경하거나 terraform.tfvars로 설정
  description = "수집 실패 또는 오류 발생 시 메일 알림을 수신할 관리자 이메일 주소"
}

# =================================================================
# 2. VPC 및 네트워크 인프라 (기본 VPC 및 공인 서브넷 조회)
# =================================================================

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# =================================================================
# 3. AWS Systems Manager Parameter Store (자격 증명 및 설정보관)
# =================================================================

locals {
  parameters = {
    "/resort/RESOM_ID"             = "dummy_id"
    "/resort/RESOM_PW"             = "dummy_pw"
    "/resort/DAEMYUNG_ID"          = "dummy_id"
    "/resort/DAEMYUNG_PW"          = "dummy_pw"
    "/resort/LOTTE_ID"             = "dummy_id"
    "/resort/LOTTE_PW"             = "dummy_pw"
    "/resort/HANHWA_ID"            = "dummy_id"
    "/resort/HANHWA_PW"            = "dummy_pw"
    "/resort/HANHWA_MEMBERSHIP_PW" = "dummy_pw"
    "/board/BOARD_ID"              = "dummy_board_id"
    "/board/BOARD_PASSWORD"        = "dummy_board_pw"
    "/board/POST_ID_LOTTE_M1"      = "9389244"
    "/board/POST_ID_LOTTE_M2"      = "9389260"
    "/board/POST_ID_LOTTE_M3"      = "9389262"
    "/board/POST_ID_RESOM_M1"      = "9389317"
    "/board/POST_ID_RESOM_M2"      = "9389320"
    "/board/POST_ID_RESOM_M3"      = "9389322"
    "/board/POST_ID_SONO_M1"      = "9389334"
    "/board/POST_ID_SONO_M2"      = "9389336"
    "/board/POST_ID_SONO_M3"      = "9389338"
    "/board/POST_ID_HANHWA_M1"      = "9389344"
    "/board/POST_ID_HANHWA_M2"      = "9389352"
    "/board/POST_ID_HANHWA_M3"      = "9389354"
  }
}

resource "aws_ssm_parameter" "credentials" {
  for_each = local.parameters
  name     = "/${var.project_name}/${var.environment}${each.key}"
  type     = "SecureString"
  value    = each.value
  lifecycle {
    ignore_changes = [value]
  }
}

# =================================================================
# 4. Amazon S3 Bucket (대시보드 웹 호스팅 및 원본 백업용)
# =================================================================

resource "aws_s3_bucket" "dashboard" {
  bucket        = "${var.project_name}-${var.environment}-dashboard-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "dashboard" {
  bucket                  = aws_s3_bucket.dashboard.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =================================================================
# 5. Amazon CloudFront (HTTPS CDN 중계 및 OAC 연동)
# =================================================================

resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "${var.project_name}-${var.environment}-oac"
  description                       = "OAC for Resort Dashboard S3 Bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "cdn" {
  origin {
    domain_name              = aws_s3_bucket.dashboard.bucket_regional_domain_name
    origin_id                = "S3Origin"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Origin"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "whitelist"
      locations        = ["KR"]
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_s3_bucket_policy" "allow_cloudfront" {
  bucket = aws_s3_bucket.dashboard.id
  policy = data.aws_iam_policy_document.s3_policy.json
}

data "aws_iam_policy_document" "s3_policy" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.dashboard.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn.arn]
    }
  }
}

# =================================================================
# 6. Amazon ECR (도커 이미지 레지스트리)
# =================================================================

resource "aws_ecr_repository" "app" {
  name                 = "${var.project_name}-repo"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

# =================================================================
# 7. AWS SNS (Simple Notification Service) - 메일 알림 설정
# =================================================================

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts-topic"
}

# 관리자 이메일 주소로 구독 생성
# 주의: 테라폼 배포 후 해당 메일 수신함에서 AWS가 보낸 'Confirm Subscription' 메일을 반드시 클릭해야 활성화됩니다.
resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.admin_email
}

# =================================================================
# 8. AWS ECS Fargate & CloudWatch Logs
# =================================================================

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}-${var.environment}"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

resource "aws_ecs_task_definition" "task" {
  family                   = "${var.project_name}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024" # 1 vCPU
  memory                   = "2048" # 2GB RAM
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "crawler-container"
      image     = "${aws_ecr_repository.app.repository_url}:latest"
      essential = true
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      environment = [
        { name = "S3_BUCKET", value = aws_s3_bucket.dashboard.id },
        { name = "SNS_TOPIC_ARN", value = aws_sns_topic.alerts.arn }
      ]
      secrets = [
        { name = "RESOM_ID", valueFrom = aws_ssm_parameter.credentials["/resort/RESOM_ID"].arn },
        { name = "RESOM_PW", valueFrom = aws_ssm_parameter.credentials["/resort/RESOM_PW"].arn },
        { name = "DAEMYUNG_ID", valueFrom = aws_ssm_parameter.credentials["/resort/DAEMYUNG_ID"].arn },
        { name = "DAEMYUNG_PW", valueFrom = aws_ssm_parameter.credentials["/resort/DAEMYUNG_PW"].arn },
        { name = "LOTTE_ID", valueFrom = aws_ssm_parameter.credentials["/resort/LOTTE_ID"].arn },
        { name = "LOTTE_PW", valueFrom = aws_ssm_parameter.credentials["/resort/LOTTE_PW"].arn },
        { name = "HANHWA_ID", valueFrom = aws_ssm_parameter.credentials["/resort/HANHWA_ID"].arn },
        { name = "HANHWA_PW", valueFrom = aws_ssm_parameter.credentials["/resort/HANHWA_PW"].arn },
        { name = "HANHWA_MEMBERSHIP_PW", valueFrom = aws_ssm_parameter.credentials["/resort/HANHWA_MEMBERSHIP_PW"].arn },
        { name = "BOARD_ID", valueFrom = aws_ssm_parameter.credentials["/board/BOARD_ID"].arn },
        { name = "BOARD_PASSWORD", valueFrom = aws_ssm_parameter.credentials["/board/BOARD_PASSWORD"].arn },
        { name = "POST_ID_LOTTE_M1", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_LOTTE_M1"].arn },
        { name = "POST_ID_LOTTE_M2", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_LOTTE_M2"].arn },
        { name = "POST_ID_LOTTE_M3", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_LOTTE_M3"].arn },
        { name = "POST_ID_RESOM_M1", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_RESOM_M1"].arn },
        { name = "POST_ID_RESOM_M2", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_RESOM_M2"].arn },
        { name = "POST_ID_RESOM_M3", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_RESOM_M3"].arn },
        { name = "POST_ID_SONO_M1", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_SONO_M1"].arn },
        { name = "POST_ID_SONO_M2", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_SONO_M2"].arn },
        { name = "POST_ID_SONO_M3", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_SONO_M3"].arn },
        { name = "POST_ID_HANHWA_M1", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_HANHWA_M1"].arn },
        { name = "POST_ID_HANHWA_M2", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_HANHWA_M2"].arn },
        { name = "POST_ID_HANHWA_M3", valueFrom = aws_ssm_parameter.credentials["/board/POST_ID_HANHWA_M3"].arn }
      ]
    }
  ])
}

# =================================================================
# 9. IAM 역할 설정 (Execution Role & Task Role)
# =================================================================

# ECS Execution Role (ECR 이미지 다운로드 및 파라미터 복호화용)
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.project_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_standard" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_policy" "ecs_execution_ssm" {
  name = "${var.project_name}-ecs-execution-ssm-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameters",
          "secretsmanager:GetSecretValue",
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_ssm_attach" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = aws_iam_policy.ecs_execution_ssm.arn
}

# ECS Task Role (파이썬 코드가 S3 업로드 및 SNS 이메일 알림 전송을 직접 수행하기 위한 권한)
resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "ecs_task_s3" {
  name = "${var.project_name}-ecs-task-s3-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.dashboard.arn,
          "${aws_s3_bucket.dashboard.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_s3_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_task_s3.arn
}

# 컨테이너 앱이 SNS 경보 메일을 직접 발행할 수 있도록 권한 부여
resource "aws_iam_policy" "ecs_task_sns" {
  name = "${var.project_name}-ecs-task-sns-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = [
          aws_sns_topic.alerts.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_sns_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_task_sns.arn
}

# =================================================================
# 10. Amazon EventBridge (크론 스케줄링 및 Fargate 트리거)
# =================================================================

resource "aws_iam_role" "eventbridge_role" {
  name = "${var.project_name}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "eventbridge_run_task" {
  name = "${var.project_name}-eventbridge-run-task-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [
          replace(aws_ecs_task_definition.task.arn, "/:\\d+$/", ":*")
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_execution_role.arn,
          aws_iam_role.ecs_task_role.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eventbridge_run_task_attach" {
  role       = aws_iam_role.eventbridge_role.name
  policy_arn = aws_iam_policy.eventbridge_run_task.arn
}

# 10.1. 리조트 크롤링 스케줄링 (평일 한국 시간 8:15, 10:15, 12:15, 14:15, 16:15)
# cron 표기는 UTC 기준이므로 한국 기준 -9시간 적용: (23:15, 01:15, 03:15, 05:15, 07:15)
resource "aws_cloudwatch_event_rule" "resort_schedule" {
  name                = "${var.project_name}-resort-rule"
  description         = "Schedule for Resort vacancy crawl (Weekdays 5 times)"
  schedule_expression = "cron(15 23,1,3,5,7 ? * MON-FRI *)"
}

resource "aws_cloudwatch_event_target" "resort_target" {
  rule      = aws_cloudwatch_event_rule.resort_schedule.name
  target_id = "ResortCrawlerTarget"
  arn       = aws_ecs_cluster.main.arn
  role_arn  = aws_iam_role.eventbridge_role.arn

  ecs_target {
    task_count          = 1
    task_definition_arn = aws_ecs_task_definition.task.arn
    launch_type         = "FARGATE"

    network_configuration {
      subnets          = data.aws_subnets.default.ids
      security_groups  = [aws_security_group.ecs_tasks.id]
      assign_public_ip = true
    }
  }

  input = jsonencode({
    containerOverrides = [
      {
        name = "crawler-container"
        environment = [
          { name = "JOB_TYPE", value = "resort" }
        ]
      }
    ]
  })
}

# 10.2. 구내식당 수집 스케줄링 (매일 한국 시간 11:30)
# UTC 기준: (02:30)
resource "aws_cloudwatch_event_rule" "cafeteria_schedule" {
  name                = "${var.project_name}-cafeteria-rule"
  description         = "Schedule for Cafeteria menu sync (Daily 1 time)"
  schedule_expression = "cron(30 2 * * ? *)"
}

resource "aws_cloudwatch_event_target" "cafeteria_target" {
  rule      = aws_cloudwatch_event_rule.cafeteria_schedule.name
  target_id = "CafeteriaTarget"
  arn       = aws_ecs_cluster.main.arn
  role_arn  = aws_iam_role.eventbridge_role.arn

  ecs_target {
    task_count          = 1
    task_definition_arn = aws_ecs_task_definition.task.arn
    launch_type         = "FARGATE"

    network_configuration {
      subnets          = data.aws_subnets.default.ids
      security_groups  = [aws_security_group.ecs_tasks.id]
      assign_public_ip = true
    }
  }

  input = jsonencode({
    containerOverrides = [
      {
        name = "crawler-container"
        environment = [
          { name = "JOB_TYPE", value = "cafeteria" }
        ]
      }
    ]
  })
}

# =================================================================
# 11. 보안 그룹 (Security Group)
# =================================================================

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Allow outbound traffic only for ECS Fargate Tasks"
  vpc_id      = data.aws_vpc.default.id

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-tasks-sg"
  }
}

# =================================================================
# 12. 최종 아웃풋 정의 (Outputs)
# =================================================================

output "cloudfront_url" {
  value       = "https://${aws_cloudfront_distribution.cdn.domain_name}"
  description = "배포된 리조트 대시보드 웹 주소 (HTTPS)"
}

output "s3_bucket_name" {
  value       = aws_s3_bucket.dashboard.id
  description = "대시보드 데이터 보관 S3 버킷명"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.app.repository_url
  description = "도커 이미지를 푸시할 ECR 리포지토리 URL"
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "생성된 ECS 클러스터 이름"
}

output "ecs_task_definition_family" {
  value       = aws_ecs_task_definition.task.family
  description = "생성된 ECS 태스크 정의 패밀리"
}

output "sns_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "생성된 에러 알림용 SNS 토픽 ARN"
}
